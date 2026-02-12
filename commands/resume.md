Resume or reattach to an existing entry and its sandbox.

Run the superintendent CLI resume command:

```bash
superintendent resume $ARGUMENTS
```

## Available flags

- `--name NAME` (required) — Name of the entry to resume

Looks up the entry in the global registry, verifies the path
and sandbox still exist, then reattaches to the running agent.

## Examples

```
/superintendent:resume --name my-repo
```
