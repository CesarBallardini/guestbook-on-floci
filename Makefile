.DEFAULT_GOAL := help

.PHONY: help all up infra build deploy rollback rollback-check idempotence smoke replace-instance urls status console \
        install qa lint format test test-integration test-e2e destroy clean

TERRAFORM := terraform -chdir=terraform

help: ## Show this list of available targets
	@grep -E '^[a-zA-Z0-9_-]+:.*## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*## "}; {printf "\033[36m%-18s\033[0m %s\n", $$1, $$2}'

all: up infra deploy urls ## From nothing to the running guestbook: up, infra, deploy, urls

up: ## Start Floci, the AWS emulator, and wait until it is healthy
	docker compose up -d --wait

infra: ## Create or update the infrastructure in the emulator (Terraform asks before it changes anything)
	$(TERRAFORM) init -input=false
	$(TERRAFORM) apply

build: ## Build the app: its wheel and its locked dependencies, in app/dist/
	$(MAKE) -C app build

deploy: build ## Build, then make a release on the instance and run it (Ansible, from its container)
	docker compose run --rm ansible

rollback: ## Run the release before the current one, on the schema as it is (migrations are never undone)
	docker compose run --rm ansible -e rollback=true

rollback-check: deploy ## Deploy, then a build with one more migration, roll back across it and check; restores what it changed
	sh ansible/check-rollback.sh

idempotence: deploy ## Deploy, then run the playbook again and fail unless that second run changes nothing
	docker compose run --rm --entrypoint sh ansible /work/ansible/check-idempotence.sh

smoke: ## Check the running stack: HTTPS answers, HTTP redirects to it, and Terraform has nothing to change
	curl --fail --silent --show-error --insecure --location --max-redirs 1 --proto-redir =https http://localhost:8080/health
	curl --fail --silent --show-error --insecure https://localhost:8443/health
	$(TERRAFORM) plan -input=false -detailed-exitcode

replace-instance: ## Make the EC2 instance again and deploy to it (messages and pictures survive)
	$(TERRAFORM) apply -replace=aws_instance.app
	$(MAKE) deploy

urls: ## Print the guestbook's URLs, the instance and the database
	$(TERRAFORM) output

status: ## List the containers behind the emulated resources, with their ports
	docker ps --filter network=guestbook-on-floci --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

console: ## Print the URL of Floci's web console (the first visit starts it)
	@echo "http://127.0.0.1:4566/_floci/ui    (see docs/floci.md)"

install: ## Sync the app's environment from the committed lockfile
	$(MAKE) -C app install

qa: lint ## Run every quality gate: Terraform and Ansible checks, then the app's (lint, types, architecture, coverage, security)
	$(MAKE) -C app qa

lint: ## Check the Terraform files and the playbook without modifying them (fmt, validate, tflint, ansible-lint)
	$(TERRAFORM) fmt -check
	$(TERRAFORM) validate
	cd terraform && tflint
	docker compose run --rm --entrypoint ansible-lint ansible

format: ## Auto-fix the formatting of the Terraform files and of the app
	$(TERRAFORM) fmt
	$(MAKE) -C app format

test: ## Run the app's unit and acceptance tests (nothing needs to be running)
	$(MAKE) -C app test

test-integration: ## Run the app's integration tests (after: make up infra)
	$(MAKE) -C app test-integration

test-e2e: ## Run the app's end-to-end tests in a browser (after: make all)
	$(MAKE) -C app test-e2e

destroy: ## Remove everything: the emulated resources, Floci, and the volume it leaves behind
	$(TERRAFORM) destroy
	docker compose down -v
	docker volume rm --force floci-aws-ec2-volumes

clean: ## Remove the app's cache and coverage artifacts
	$(MAKE) -C app clean
