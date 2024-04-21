package:
	python3 -m build

upload:
	python3 -m twine upload dist/*

prepare_env:
	pip3 install --break-system-package build
	pip3 install --break-system-package twine

