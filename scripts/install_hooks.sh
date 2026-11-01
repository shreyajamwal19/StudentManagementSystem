#!/usr/bin/env bash
set -e
cd "$(git rev-parse --show-toplevel)"
printf '#!/usr/bin/env bash\nexec ./scripts/check_secrets.sh\n' > .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
echo "pre-commit secret scan installed"
