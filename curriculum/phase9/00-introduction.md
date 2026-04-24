# Phase 9 — Production CI/CD & Platform Engineering

Phase 8 built the dashboard and auth. Phase 9 makes AOIS ship itself.

Every code change automatically: lints, tests, scans for vulnerabilities, signs the image, pushes to GHCR, and deploys to both Hetzner and EKS via ArgoCD — with zero manual steps.

**v28 — GitHub Actions + Dagger**: Full CI/CD pipeline. PR gate. Production deploy on merge.
**v29 — Weights & Biases**: Track every prompt change as a measurable experiment.
**v30 — Internal Developer Platform**: Self-service portal. Crossplane. Pulumi. Semantic Kernel.

After Phase 9, AOIS is a production-grade platform: it deploys itself, tracks its own quality over time, and can be provisioned as a tenant for new teams without manual intervention.
