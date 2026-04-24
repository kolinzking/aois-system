"""AOIS CI pipeline via Dagger — runs identically locally and in GitHub Actions."""
import anyio
import dagger


async def pipeline():
    async with dagger.Connection() as client:
        src = client.host().directory(
            ".",
            exclude=["dashboard/node_modules", "__pycache__", ".git", "*.pyc"],
        )

        python = (
            client.container()
            .from_("python:3.11-slim")
            .with_directory("/app", src)
            .with_workdir("/app")
            .with_exec(["pip", "install", "-q", "-r", "requirements.txt", "ruff", "pytest"])
        )

        print("Running lint...")
        lint = python.with_exec(["ruff", "check", ".", "--ignore", "E501"])
        print(await lint.stdout())

        print("Building image...")
        image = client.container().build(src)
        addr = await image.publish("ghcr.io/kolinzking/aois:dagger-local")
        print(f"Published: {addr}")


if __name__ == "__main__":
    anyio.run(pipeline)
