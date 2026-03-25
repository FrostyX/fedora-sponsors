activity:
	python activity.py

groups:
	python groups.py

build:
	python sponsors.py

check:
	python check.py

deps:
	sudo dnf install -y \
		python3-fasjson-client \
		python3-jinja2 \
		python3-pyyaml \
		python3-pytz \
		python3-munch \
		python3-bugzilla \
		python3-pylibravatar \
		python3-requests \
		python3-beautifulsoup4 \
		python3-fasjson-client
