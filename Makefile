PY := /opt/homebrew/bin/python3
PKG := cmux-helper.alfredworkflow

.PHONY: test link unlink package

test:
	$(PY) -m unittest discover -s tests -t . -v

package:
	rm -f "$(PKG)"
	zip -r "$(PKG)" info.plist cmuxhelper.py icon.png README.md -x '*.pyc'
	@echo "Built $(PKG)"
