"""Docker container status queries."""


def get_container_statuses(client, watched):
    results = []

    containers = {
        c.name: c
        for c in client.containers.list(all=True)
    }

    names = (
        watched
        if watched
        else list(containers.keys())
    )

    for name in names:
        container = containers.get(name)

        if container is None:
            results.append(
                (name, "missing", False)
            )
            continue

        container.reload()

        status = container.status
        health = None

        health_info = (
            container.attrs
            .get("State", {})
            .get("Health")
        )

        if health_info:
            health = (
                health_info.get("Status")
                == "healthy"
            )

        results.append(
            (
                name,
                status,
                health,
            )
        )

    return results


def is_problem(status, healthy):
    if status != "running":
        return True

    if healthy is False:
        return True

    return False
