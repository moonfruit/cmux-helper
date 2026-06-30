PY := /opt/homebrew/bin/python3
WF_DIR := $(HOME)/Workspace.localized/env/preferences/alfred/Alfred.alfredpreferences/workflows
LINK := $(WF_DIR)/user.workflow.CMUXHELPER-DEV
PKG := cmux-helper.alfredworkflow

.PHONY: test link unlink package

test:
	$(PY) -m unittest discover -s tests -t . -v

link:
	ln -sfn "$(CURDIR)" "$(LINK)"
	@echo "Linked -> $(LINK)"

unlink:
	rm -f "$(LINK)"

package:
	rm -f "$(PKG)"
	zip -r "$(PKG)" info.plist cmuxhelper.py README.md -x '*.pyc'
	@echo "Built $(PKG)"
