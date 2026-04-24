"""Provision AOIS infrastructure for a new tenant using Pulumi + Python."""
import pulumi
import os

config = pulumi.Config()
tenant_name = config.require("tenantName")
model_tier = config.get("modelTier", "standard")
region = config.get("region", "nbg1")


def build_helm_values() -> dict:
    values = {
        "image": {"tag": os.getenv("AOIS_IMAGE_TAG", "latest")},
        "resources": {
            "limits": {"memory": "2Gi" if model_tier == "premium" else "1Gi"},
            "requests": {"memory": "512Mi" if model_tier == "premium" else "256Mi"},
        },
        "replicaCount": 2 if model_tier == "premium" else 1,
    }
    if model_tier == "premium":
        values["clickhouse"] = {"enabled": True}
        values["agentEvals"] = {"schedule": "0 * * * *"}  # hourly evals for premium
    return values


try:
    import pulumi_kubernetes as k8s

    namespace = k8s.core.v1.Namespace(
        f"{tenant_name}-aois",
        metadata=k8s.meta.v1.ObjectMetaArgs(
            name=f"{tenant_name}-aois",
            labels={"aois.io/tenant": tenant_name, "aois.io/tier": model_tier},
        ),
    )

    release = k8s.helm.v3.Release(
        f"aois-{tenant_name}",
        chart="./charts/aois",
        namespace=namespace.metadata.name,
        values=build_helm_values(),
        opts=pulumi.ResourceOptions(depends_on=[namespace]),
    )

    pulumi.export("namespace", namespace.metadata.name)
    pulumi.export("helm_release_status", release.status)

except ImportError:
    pulumi.log.warn("pulumi_kubernetes not installed — run: pip install pulumi-kubernetes")
    pulumi.export("namespace", f"{tenant_name}-aois (preview only)")
