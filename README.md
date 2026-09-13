# kuestion — a KDE desktop AI agent where everything is a plugin

The kernel is tiny: a **plugin loader** and an **event bus**. There is no service
registry — every action travels through the bus as a keyed event, so any
component can be replaced without others noticing.

Status: early scaffold. See `KUESTION_PLAN.md` for the full design and
phase-by-phase implementation plan.

## Layout

```
kernel/           plugin loader + event bus (with tests in kernel/tests/)
plugins/<name>/   drop-in plugins (code + tests/ beside each other)
configs/          committed defaults (config.json itself is user-local)
main.py           entry point
```
