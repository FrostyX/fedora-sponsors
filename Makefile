activity:
	python activity.py

groups:
	python groups.py

build:
	python sponsors.py

deploy:
	git clone "ssh://git@pagure.io/docs/fedora-sponsors.git" _build/deploy
	cp -r _build/production/* _build/deploy && \
	cd _build/deploy && \
	git add . && \
	git commit -av -m "New build" && \
	git push
	rm -rf _build/deploy
