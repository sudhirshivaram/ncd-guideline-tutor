.PHONY: index backend eval

index:
	cd backend && PYTHONPATH=. python -m app.rag.indexing

backend:
	cd backend && PYTHONPATH=. uvicorn app.main:app --reload --port 8000

eval:
	cd backend && PYTHONPATH=. python -m app.eval.runner
