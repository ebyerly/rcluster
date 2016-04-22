git-dev:
	@pip freeze > requirements.txt
	@git add --all
	@git --no-pager diff HEAD
	@echo "Please type commit message:";\
	read commit_message;\
	git commit -m "$$commit_message";\
