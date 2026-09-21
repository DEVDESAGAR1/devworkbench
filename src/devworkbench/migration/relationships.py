"""Inter-resource dependency and relationship detection for Kubernetes manifests."""

from typing import Any

from devworkbench.migration.models import (
    DiscoveredResource,
    RelationshipStatus,
    RelationshipType,
    ResourceRelationship,
)


class RelationshipAnalyzer:
    """Analyzes cross-resource references and dependencies among discovered Kubernetes manifests."""

    @classmethod
    def analyze(cls, resources: list[DiscoveredResource]) -> list[ResourceRelationship]:
        """Analyze all resources and return detected relationships and missing references."""
        # Index resources by (kind.lower(), name.lower())
        resource_index: dict[tuple[str, str], DiscoveredResource] = {
            (r.kind.lower(), r.name.lower()): r for r in resources
        }

        relationships: list[ResourceRelationship] = []

        for r in resources:
            kind_lower = r.kind.lower()

            # 1. HPA -> Workload
            if kind_lower == "horizontalpodautoscaler":
                cls._analyze_hpa(r, resource_index, relationships)

            # 2. Ingress -> Service
            elif kind_lower == "ingress":
                cls._analyze_ingress(r, resource_index, relationships)

            # 3. Workloads (Deployment, StatefulSet, DaemonSet, Job, CronJob, Pod) -> ConfigMap, Secret, PVC, SA
            elif kind_lower in ("deployment", "statefulset", "daemonset", "job", "cronjob", "pod"):
                cls._analyze_workload(r, resource_index, relationships)

            # 4. Service -> Workload via selector
            elif kind_lower == "service":
                cls._analyze_service(r, resources, relationships)

        # Sort relationships deterministically
        relationships.sort(
            key=lambda rel: (
                rel.source_kind,
                rel.source_name,
                rel.rel_type.value,
                rel.target_kind,
                rel.target_name,
            )
        )
        return relationships

    @classmethod
    def _analyze_hpa(
        cls,
        hpa: DiscoveredResource,
        index: dict[tuple[str, str], DiscoveredResource],
        out: list[ResourceRelationship],
    ) -> None:
        target_ref = hpa.spec.get("scaleTargetRef", {})
        if not isinstance(target_ref, dict):
            return

        target_kind = str(target_ref.get("kind", "Deployment"))
        target_name = str(target_ref.get("name", ""))
        if not target_name:
            return

        exists = (target_kind.lower(), target_name.lower()) in index
        status = RelationshipStatus.REFERENCED_AND_PRESENT if exists else RelationshipStatus.REFERENCED_BUT_MISSING
        detail = f"HPA scales {target_kind}/{target_name}"

        out.append(
            ResourceRelationship(
                source_kind=hpa.kind,
                source_name=hpa.name,
                target_kind=target_kind,
                target_name=target_name,
                rel_type=RelationshipType.HPA_TARGET,
                status=status,
                details=detail,
            )
        )

    @classmethod
    def _analyze_ingress(
        cls,
        ingress: DiscoveredResource,
        index: dict[tuple[str, str], DiscoveredResource],
        out: list[ResourceRelationship],
    ) -> None:
        # Default backend
        default_backend = ingress.spec.get("defaultBackend", {})
        svc_name = (
            default_backend.get("service", {}).get("name")
            if isinstance(default_backend.get("service"), dict)
            else default_backend.get("serviceName")
        )
        if svc_name and isinstance(svc_name, str):
            exists = ("service", svc_name.lower()) in index
            out.append(
                ResourceRelationship(
                    source_kind=ingress.kind,
                    source_name=ingress.name,
                    target_kind="Service",
                    target_name=svc_name,
                    rel_type=RelationshipType.INGRESS_BACKEND,
                    status=RelationshipStatus.REFERENCED_AND_PRESENT if exists else RelationshipStatus.REFERENCED_BUT_MISSING,
                    details=f"Default backend routes to Service/{svc_name}",
                )
            )

        # Rules
        rules = ingress.spec.get("rules", [])
        if isinstance(rules, list):
            for rule in rules:
                if not isinstance(rule, dict):
                    continue
                http_rule = rule.get("http", {})
                if not isinstance(http_rule, dict):
                    continue
                paths = http_rule.get("paths", [])
                if not isinstance(paths, list):
                    continue
                for path_item in paths:
                    if not isinstance(path_item, dict):
                        continue
                    backend = path_item.get("backend", {})
                    if not isinstance(backend, dict):
                        continue
                    b_svc = (
                        backend.get("service", {}).get("name")
                        if isinstance(backend.get("service"), dict)
                        else backend.get("serviceName")
                    )
                    if b_svc and isinstance(b_svc, str):
                        exists = ("service", b_svc.lower()) in index
                        out.append(
                            ResourceRelationship(
                                source_kind=ingress.kind,
                                source_name=ingress.name,
                                target_kind="Service",
                                target_name=b_svc,
                                rel_type=RelationshipType.INGRESS_BACKEND,
                                status=RelationshipStatus.REFERENCED_AND_PRESENT if exists else RelationshipStatus.REFERENCED_BUT_MISSING,
                                details=f"Path '{path_item.get('path', '/')}' routes to Service/{b_svc}",
                            )
                        )

    @classmethod
    def _extract_pod_spec(cls, workload: DiscoveredResource) -> dict[str, Any]:
        """Extract pod spec from Deployment, StatefulSet, DaemonSet, Job, or CronJob."""
        spec = workload.spec
        if workload.kind.lower() == "cronjob":
            return (
                spec.get("jobTemplate", {})
                .get("spec", {})
                .get("template", {})
                .get("spec", {})
            )
        if "template" in spec and isinstance(spec["template"], dict):
            return spec["template"].get("spec", {})
        return spec

    @classmethod
    def _analyze_workload(
        cls,
        workload: DiscoveredResource,
        index: dict[tuple[str, str], DiscoveredResource],
        out: list[ResourceRelationship],
    ) -> None:
        pod_spec = cls._extract_pod_spec(workload)
        if not isinstance(pod_spec, dict):
            return

        # 1. ServiceAccount
        sa_name = pod_spec.get("serviceAccountName") or pod_spec.get("serviceAccount")
        if sa_name and isinstance(sa_name, str) and sa_name != "default":
            exists = ("serviceaccount", sa_name.lower()) in index
            out.append(
                ResourceRelationship(
                    source_kind=workload.kind,
                    source_name=workload.name,
                    target_kind="ServiceAccount",
                    target_name=sa_name,
                    rel_type=RelationshipType.SERVICE_ACCOUNT,
                    status=RelationshipStatus.REFERENCED_AND_PRESENT if exists else RelationshipStatus.REFERENCED_BUT_MISSING,
                    details=f"Pod runs with ServiceAccount/{sa_name}",
                )
            )

        # 2. Containers (env, envFrom)
        containers = pod_spec.get("containers", [])
        if isinstance(containers, list):
            for c in containers:
                if not isinstance(c, dict):
                    continue
                # envFrom
                env_from = c.get("envFrom", [])
                if isinstance(env_from, list):
                    for ef in env_from:
                        if not isinstance(ef, dict):
                            continue
                        cm_ref = ef.get("configMapRef", {})
                        if isinstance(cm_ref, dict) and cm_ref.get("name"):
                            cm_name = str(cm_ref["name"])
                            exists = ("configmap", cm_name.lower()) in index
                            out.append(
                                ResourceRelationship(
                                    source_kind=workload.kind,
                                    source_name=workload.name,
                                    target_kind="ConfigMap",
                                    target_name=cm_name,
                                    rel_type=RelationshipType.ENV_CONFIGMAP,
                                    status=RelationshipStatus.REFERENCED_AND_PRESENT if exists else RelationshipStatus.REFERENCED_BUT_MISSING,
                                    details=f"Container '{c.get('name')}' loads envFrom ConfigMap/{cm_name}",
                                )
                            )
                        sec_ref = ef.get("secretRef", {})
                        if isinstance(sec_ref, dict) and sec_ref.get("name"):
                            sec_name = str(sec_ref["name"])
                            exists = ("secret", sec_name.lower()) in index
                            out.append(
                                ResourceRelationship(
                                    source_kind=workload.kind,
                                    source_name=workload.name,
                                    target_kind="Secret",
                                    target_name=sec_name,
                                    rel_type=RelationshipType.ENV_SECRET,
                                    status=RelationshipStatus.REFERENCED_AND_PRESENT if exists else RelationshipStatus.REFERENCED_BUT_MISSING,
                                    details=f"Container '{c.get('name')}' loads envFrom Secret/{sec_name}",
                                )
                            )

                # env valueFrom
                env_list = c.get("env", [])
                if isinstance(env_list, list):
                    for e in env_list:
                        if not isinstance(e, dict):
                            continue
                        vf = e.get("valueFrom", {})
                        if not isinstance(vf, dict):
                            continue
                        cm_key_ref = vf.get("configMapKeyRef", {})
                        if isinstance(cm_key_ref, dict) and cm_key_ref.get("name"):
                            cm_name = str(cm_key_ref["name"])
                            exists = ("configmap", cm_name.lower()) in index
                            out.append(
                                ResourceRelationship(
                                    source_kind=workload.kind,
                                    source_name=workload.name,
                                    target_kind="ConfigMap",
                                    target_name=cm_name,
                                    rel_type=RelationshipType.ENV_CONFIGMAP,
                                    status=RelationshipStatus.REFERENCED_AND_PRESENT if exists else RelationshipStatus.REFERENCED_BUT_MISSING,
                                    details=f"Env variable '{e.get('name')}' references ConfigMap/{cm_name}",
                                )
                            )
                        sec_key_ref = vf.get("secretKeyRef", {})
                        if isinstance(sec_key_ref, dict) and sec_key_ref.get("name"):
                            sec_name = str(sec_key_ref["name"])
                            exists = ("secret", sec_name.lower()) in index
                            out.append(
                                ResourceRelationship(
                                    source_kind=workload.kind,
                                    source_name=workload.name,
                                    target_kind="Secret",
                                    target_name=sec_name,
                                    rel_type=RelationshipType.ENV_SECRET,
                                    status=RelationshipStatus.REFERENCED_AND_PRESENT if exists else RelationshipStatus.REFERENCED_BUT_MISSING,
                                    details=f"Env variable '{e.get('name')}' references Secret/{sec_name}",
                                )
                            )

        # 3. Volumes (ConfigMap, Secret, PVC)
        volumes = pod_spec.get("volumes", [])
        if isinstance(volumes, list):
            for v in volumes:
                if not isinstance(v, dict):
                    continue
                # ConfigMap volume
                cm_vol = v.get("configMap", {})
                if isinstance(cm_vol, dict) and cm_vol.get("name"):
                    cm_name = str(cm_vol["name"])
                    exists = ("configmap", cm_name.lower()) in index
                    out.append(
                        ResourceRelationship(
                            source_kind=workload.kind,
                            source_name=workload.name,
                            target_kind="ConfigMap",
                            target_name=cm_name,
                            rel_type=RelationshipType.VOLUME_CONFIGMAP,
                            status=RelationshipStatus.REFERENCED_AND_PRESENT if exists else RelationshipStatus.REFERENCED_BUT_MISSING,
                            details=f"Volume '{v.get('name')}' mounts ConfigMap/{cm_name}",
                        )
                    )
                # Secret volume
                sec_vol = v.get("secret", {})
                if isinstance(sec_vol, dict) and sec_vol.get("secretName"):
                    sec_name = str(sec_vol["secretName"])
                    exists = ("secret", sec_name.lower()) in index
                    out.append(
                        ResourceRelationship(
                            source_kind=workload.kind,
                            source_name=workload.name,
                            target_kind="Secret",
                            target_name=sec_name,
                            rel_type=RelationshipType.VOLUME_SECRET,
                            status=RelationshipStatus.REFERENCED_AND_PRESENT if exists else RelationshipStatus.REFERENCED_BUT_MISSING,
                            details=f"Volume '{v.get('name')}' mounts Secret/{sec_name}",
                        )
                    )
                # PVC volume
                pvc_vol = v.get("persistentVolumeClaim", {})
                if isinstance(pvc_vol, dict) and pvc_vol.get("claimName"):
                    pvc_name = str(pvc_vol["claimName"])
                    exists = ("persistentvolumeclaim", pvc_name.lower()) in index
                    out.append(
                        ResourceRelationship(
                            source_kind=workload.kind,
                            source_name=workload.name,
                            target_kind="PersistentVolumeClaim",
                            target_name=pvc_name,
                            rel_type=RelationshipType.VOLUME_PVC,
                            status=RelationshipStatus.REFERENCED_AND_PRESENT if exists else RelationshipStatus.REFERENCED_BUT_MISSING,
                            details=f"Volume '{v.get('name')}' claims PVC/{pvc_name}",
                        )
                    )

    @classmethod
    def _analyze_service(
        cls,
        service: DiscoveredResource,
        all_resources: list[DiscoveredResource],
        out: list[ResourceRelationship],
    ) -> None:
        selector = service.spec.get("selector", {})
        if not isinstance(selector, dict) or not selector:
            return

        # Find any workload matching selector
        for r in all_resources:
            if r.kind.lower() in ("deployment", "statefulset", "daemonset"):
                template = r.spec.get("template", {})
                pod_labels = template.get("metadata", {}).get("labels", {}) if isinstance(template, dict) else {}
                if isinstance(pod_labels, dict):
                    # Check if all selector key-values are in pod_labels
                    if all(pod_labels.get(k) == str(v) for k, v in selector.items()):
                        out.append(
                            ResourceRelationship(
                                source_kind=service.kind,
                                source_name=service.name,
                                target_kind=r.kind,
                                target_name=r.name,
                                rel_type=RelationshipType.SERVICE_SELECTOR,
                                status=RelationshipStatus.REFERENCED_AND_PRESENT,
                                details=f"Service selector matches pod template of {r.kind}/{r.name}",
                            )
                        )
