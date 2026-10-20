# xsnapshot-pc — development tasks.
#
# Every target operates on this checkout only; nothing is uploaded.

.PHONY: help snapshot validate test check
.DEFAULT_GOAL := help

help:
	@echo "xsnapshot-pc targets:"
	@echo "  snapshot  capture a new sanitized snapshot  (./bin/xsnapshot collect)"
	@echo "  validate  validate the newest snapshot and its artifact hashes  (./bin/xsnapshot validate)"
	@echo "  test      run the unit tests  (python3 -m unittest discover -s tests -v)"
	@echo "  check     run the tests, then validate the newest snapshot"

snapshot:
	./bin/xsnapshot collect

validate:
	./bin/xsnapshot validate

test:
	python3 -m unittest discover -s tests -v

check: test validate