## What does this PR do?

<!-- Describe the change and why it's needed. Link any related issue. -->

## Testing

- [ ] Backend tests pass (`cd backend && pytest tests/ -v`)
- [ ] Frontend build passes (`cd frontend && npm run build`)
- [ ] Manually tested the affected flow
- [ ] No `.env` files, secrets, or `.tfvars` committed

## Checklist

- [ ] `ruff check app/ tests/` clean
- [ ] `tsc --noEmit` clean
- [ ] Migration added if the schema changed (`alembic revision --autogenerate`)
