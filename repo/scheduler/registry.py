from collections.abc import Callable

Handler = Callable[..., None]

JOB_HANDLERS: dict[str, Handler] = {}


def register_job(name: str):
    def decorator(func: Handler):
        JOB_HANDLERS[name] = func
        return func

    return decorator
