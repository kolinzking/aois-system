"""Claude Computer Use agent that navigates Grafana to investigate incidents."""
import anthropic
import base64
import os
import time
from dataclasses import dataclass, field

_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

COMPUTER_USE_TOOLS = [
    {
        "type": "computer_20241022",
        "name": "computer",
        "display_width_px": 1280,
        "display_height_px": 800,
        "display_number": 1,
    }
]


@dataclass
class ComputerUseResult:
    task: str
    actions_taken: list[dict] = field(default_factory=list)
    final_screenshot_b64: str = ""
    findings: str = ""
    success: bool = False
    steps_taken: int = 0


class GrafanaComputerUseAgent:
    """Claude controls Grafana via Playwright to investigate incidents."""

    def __init__(self, grafana_url: str):
        self._grafana_url = grafana_url
        self._page = None
        self._playwright = None
        self._browser = None

    def __enter__(self):
        try:
            from playwright.sync_api import sync_playwright
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(headless=True)
            self._page = self._browser.new_page(viewport={"width": 1280, "height": 800})
            self._page.goto(self._grafana_url, timeout=15000)
        except Exception as e:
            raise RuntimeError(f"Failed to launch Playwright browser: {e}. Run: playwright install chromium") from e
        return self

    def __exit__(self, *_):
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()

    def _take_screenshot(self) -> str:
        screenshot_bytes = self._page.screenshot()
        return base64.standard_b64encode(screenshot_bytes).decode("utf-8")

    def _execute_action(self, action: dict) -> str:
        action_type = action.get("action")

        if action_type == "click":
            x, y = action["coordinate"]
            self._page.mouse.click(x, y)
            time.sleep(0.5)
        elif action_type == "double_click":
            x, y = action["coordinate"]
            self._page.mouse.dblclick(x, y)
            time.sleep(0.5)
        elif action_type == "type":
            self._page.keyboard.type(action["text"])
            time.sleep(0.3)
        elif action_type == "key":
            self._page.keyboard.press(action["key"])
            time.sleep(0.3)
        elif action_type == "scroll":
            x, y = action.get("coordinate", (640, 400))
            direction = action.get("scroll_direction", "down")
            amount = action.get("scroll_amount", 3)
            delta = amount * 100 if direction == "down" else -amount * 100
            self._page.mouse.wheel(0, delta)
            time.sleep(0.3)

        return self._take_screenshot()

    def investigate(self, task: str, max_steps: int = 10) -> ComputerUseResult:
        """Run Claude Computer Use to investigate a Grafana incident."""
        actions: list[dict] = []
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": "image/png", "data": self._take_screenshot()},
                    },
                    {
                        "type": "text",
                        "text": (
                            f"You are an SRE investigating a Kubernetes incident in Grafana.\n\n"
                            f"Task: {task}\n\n"
                            f"Use the computer tool to navigate the dashboard. "
                            f"When you have gathered enough information to answer, "
                            f"provide a final summary of your findings without using any more tools."
                        ),
                    },
                ],
            }
        ]

        for step in range(max_steps):
            response = _client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=4096,
                tools=COMPUTER_USE_TOOLS,
                messages=messages,
            )

            if response.stop_reason == "end_turn":
                findings = next(
                    (block.text for block in response.content if hasattr(block, "text")),
                    "No findings extracted.",
                )
                return ComputerUseResult(
                    task=task,
                    actions_taken=actions,
                    final_screenshot_b64=self._take_screenshot(),
                    findings=findings,
                    success=True,
                    steps_taken=step + 1,
                )

            tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
            messages.append({"role": "assistant", "content": response.content})

            tool_results = []
            for tool_block in tool_use_blocks:
                if tool_block.name == "computer":
                    action = tool_block.input
                    actions.append(action)
                    new_screenshot = self._execute_action(action)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tool_block.id,
                        "content": [
                            {
                                "type": "image",
                                "source": {"type": "base64", "media_type": "image/png", "data": new_screenshot},
                            }
                        ],
                    })

            if tool_results:
                messages.append({"role": "user", "content": tool_results})

        return ComputerUseResult(
            task=task,
            actions_taken=actions,
            final_screenshot_b64=self._take_screenshot(),
            findings="Max steps reached without conclusion.",
            success=False,
            steps_taken=max_steps,
        )
