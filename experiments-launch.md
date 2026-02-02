
## Run experiment against openai only step 2 and analyzing data

./run_experiment_openai.sh 01_full_stories_test --skip-step1 --model gpt-4o

## Run full experiment against openai
./run_experiment_openai.sh 01_full_stories_test --model gpt-4o

## Run experiment step 2 against openai with limited chapters

./run_experiment_openai.sh 05_openai_one_book --skip-step1 --model gpt-5-mini-2025-08-07 --max-chapters 17 --stories "Harry Potter"


## Run experiment step 2 against local llm with limited chapters

python scripts/run_narrative_experiment_refactored.py --step 2 --experiment-name 02_llama_refinement --api-mode local --engine --split-extraction --stories "Harry Potter" --llm-timeout 600 --max-chapters 5


## Run experiment step 2 against local llm

python scripts/run_narrative_experiment_refactored.py --step 2 --experiment-name 02_llama_refinement --api-mode local --engine --split-extraction --stories "Harry Potter" --llm-timeout 600