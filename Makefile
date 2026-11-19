.PHONY: run test clean

run:
	python3 src/depgraph.py config.xml --show-config

test:
	python3 -m unittest discover -s tests -v

clean:
	rm -rf __pycache__ src/__pycache__ tests/__pycache__ graph.svg
