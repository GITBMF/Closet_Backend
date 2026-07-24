#!/usr/bin/env bash
# Verify every delivered file is at the right path (checks its first line).
ok=0; bad=0
check() {
  path="$1"; expect="$2"
  if [ ! -f "$path" ]; then printf '  MISSING  %s\n' "$path"; bad=$((bad+1)); return; fi
  first=$(head -1 "$path")
  case "$first" in
    *"$expect"*) ok=$((ok+1)) ;;
    *) printf '  WRONG    %s\n           got: %s\n' "$path" "$first"; bad=$((bad+1)) ;;
  esac
}
check app/main.py                            "FastAPI application factory"
check app/core/config.py                     "Application settings"
check app/core/database.py                   "Async SQLAlchemy engine"
check app/core/security.py                   "Security primitives"
check app/core/exceptions.py                 "Domain exceptions"
check app/db/base.py                         "Declarative base"
check app/db/registry.py                     "Import every module"
check app/modules/identity/constants.py      "Roles, permissions and the RBAC matrix"
check app/modules/identity/models.py         "Identity models"
check app/modules/identity/schemas.py        "Pydantic contracts"
check app/modules/identity/repository.py     "Identity repository"
check app/modules/identity/service.py        "Identity business rules"
check app/modules/identity/router.py         "Identity HTTP layer"
check app/modules/identity/dependencies.py   "FastAPI dependencies"
check app/ops/admin.py                       "Internal operations panel"
check app/ops/auth.py                        "Authentication for the internal"
check tests/test_identity.py                 "Integration tests for the identity"
echo
echo "  $ok correct, $bad problem(s)"