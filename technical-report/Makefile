# Build the technical report.
#
# tectonic is used rather than the system TeX because it carries its own
# package bundle: the minimal TeX Live installs commonly found on macOS are
# missing pgfplots, tcolorbox and the Libertinus/Plex font packages this
# report depends on. tectonic fetches them once and caches them, so every
# build after the first is offline.

# NOT named TEX: that is a built-in GNU Make variable (TEX = tex), so `?=`
# never overrides it and the build silently runs plain `tex`, which then
# hangs on an interactive error prompt instead of failing.
TECTONIC ?= tectonic
PYTHON   ?= ../.venv/bin/python
OUT      := _build
SOURCES  := report.tex preamble.tex $(wildcard figures/*.tex)
DATA     := $(wildcard data/*.tex) $(wildcard data/*.csv)

.PHONY: all data clean distclean check

all: report.pdf

## report.pdf -- the deliverable, checked in so it can be read without a
## TeX toolchain. Intermediates stay in $(OUT), which is ignored.
report.pdf: $(OUT)/report.pdf
	@cp $< $@
	@echo "report.pdf updated -- commit it if the sources changed"

$(OUT)/report.pdf: $(SOURCES) $(DATA) | $(OUT)
	$(TECTONIC) -X compile report.tex --outdir $(OUT)

$(OUT):
	@mkdir -p $(OUT)

## data -- regenerate every plot coordinate from the committed results
data:
	$(PYTHON) make_data.py

## check -- fail if the committed figure data or PDF is stale
check: data all
	@if git diff --quiet -- data report.pdf; then \
	  echo "figure data and report.pdf are current"; \
	else \
	  echo "ERROR: rebuilding changed committed files -- commit the result."; \
	  git --no-pager diff --stat -- data report.pdf; exit 1; \
	fi

clean:
	@rm -rf $(OUT)

distclean: clean
	@rm -f data/*.tex data/*.csv
