ENV ?= nonprod
STATE_BUCKET_REGION ?= ap-southeast-1

ifneq ($(ENV),nonprod)
ifneq ($(ENV),prod)
$(error ENV must be nonprod or prod)
endif
endif

TF := terraform -chdir=envs/$(ENV)
ROOTS := bootstrap/state-backend envs/nonprod envs/prod envs/gke envs/aks modules/cost-reporting modules/cluster

.PHONY: validate lint init plan apply destroy

lint:
	tflint --recursive --config="$(CURDIR)/.tflint.hcl"

validate:
	terraform fmt -check -recursive
	@set -eu; for root in $(ROOTS); do \
		terraform -chdir="$$root" init -backend=false -input=false; \
		terraform -chdir="$$root" validate; \
		terraform -chdir="$$root" test; \
	done

init:
	@test -n "$(STATE_BUCKET)" || { echo 'Set STATE_BUCKET to the bootstrap output.' >&2; exit 2; }
	$(TF) init -input=false -backend-config="bucket=$(STATE_BUCKET)" -backend-config="region=$(STATE_BUCKET_REGION)"

plan: init
	$(TF) plan

apply: init
	$(TF) apply

destroy: init
	$(TF) destroy
