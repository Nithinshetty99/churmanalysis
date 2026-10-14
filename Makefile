.PHONY: setup data test dashboard powerbi all clean

setup:
	pip install -r requirements.txt

data:            ## simulate, load SQL, run every analysis, write outputs/
	python -m churn_platform.pipeline

test:
	python -m pytest -q

powerbi:         ## rebuild Power BI tables and preview images
	python powerbi/build_powerbi_data.py
	python powerbi/render_previews.py

dashboard:
	streamlit run dashboard/app.py

all: data test

clean:
	rm -rf data/*.csv data/*.db data/*.json outputs/*.csv outputs/*.json outputs/figures/*.png .pytest_cache
