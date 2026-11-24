ENV ?= nonprod
PYTHON ?= python3
STATE_BUCKET_REGION ?= ap-southeast-1

TF := terraform -chdir=envs/$(ENV)
ROOTS := bootstrap/state-backend envs/nonprod envs/prod envs/gke envs/aks \
	modules/budgets modules/cluster modules/cost-reporting modules/iam-github-oidc \
	modules/karpenter modules/network

.PHONY: validate lint test check-env init plan apply destroy

lint:
	tflint --recursive --config="$(CURDIR)/.tflint.hcl"

test:
	$(PYTHON) -m unittest discover -s tests -v

validate:
	terraform fmt -check -recursive
	@set -eu; for root in $(ROOTS); do \
		terraform -chdir="$$root" init -backend=false -input=false; \
		terraform -chdir="$$root" validate; \
		terraform -chdir="$$root" test; \
	done

check-env:
	@case "$(ENV)" in \
		nonprod|prod|aks|gke) ;; \
		*) echo "ENV must be nonprod, prod, aks, or gke (got '$(ENV)')" >&2; exit 2 ;; \
	esac

init: check-env
	@if [ "$(ENV)" = "nonprod" ] || [ "$(ENV)" = "prod" ]; then \
		test -n "$(STATE_BUCKET)" || { echo 'Set STATE_BUCKET to the bootstrap output.' >&2; exit 2; }; \
		$(TF) init -input=false -backend-config="bucket=$(STATE_BUCKET)" -backend-config="region=$(STATE_BUCKET_REGION)"; \
	else \
		$(TF) init -input=false; \
	fi

plan: init
	$(TF) plan

apply: init
	$(TF) apply

destroy: init
	$(TF) destroy
