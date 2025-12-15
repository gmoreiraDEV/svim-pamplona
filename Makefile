IMAGE_NAME ?= gmoreiradev/svim-maria
IMAGE_TAG ?= latest
DOCKERFILE ?= Dockerfile
CONTEXT ?= .

help:
	@echo - make env - Copia o arquivo .env.example para o arquivo .env
	@echo - make test_tool - Teste as tools sem mostrar detalhes
	@echo - make test_tool_verbose - Testa as tools mostrando todos os detalhes de execução
	@echo - make compile-deps - Criar o arquivo requirements.txt
	@echo - make build-image - Faz o build da imagem Docker para ser utilizada no Kestra
	@echo - make re-build-image - Faz o re-build da ultima imagem do Docker criada
	@echo - make push-image - Faz o push da imagem buildade para o Docker Hub
	@echo - make build-push-image - Executa os 2 comando de buildar e fazer o push para o Docker Hub

env: 
	cp .env.example .env

test_tool:
	python3 -m pytest -q tests/test_tools.py

test_tool_verbose:
	python3 -m pytest -s -q tests/test_tools.py

compile-deps:
	pip-compile requirements.in

build-image:
	docker buildx build \
		--platform linux/amd64 \
		-f $(DOCKERFILE) \
		-t $(IMAGE_NAME):$(IMAGE_TAG) \
		$(CONTEXT)

re-build-image:
	docker buildx build \
		--platform linux/amd64 \
		-f $(DOCKERFILE) \
		-t $(IMAGE_NAME):$(IMAGE_TAG) \
		$(CONTEXT) --no-cache

push-image:
	docker buildx build \
		--platform linux/amd64 \
		-f $(DOCKERFILE) \
		-t $(IMAGE_NAME):$(IMAGE_TAG) \
		--push \
		$(CONTEXT)

build-push-image: push-image
