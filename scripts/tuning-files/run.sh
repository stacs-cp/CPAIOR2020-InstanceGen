cp problem.eprime generator.eprime detailed-output/

irace --seed <seed> --scenario scenario.txt --parameter-file params.irace --train-instances-file instances --exec-dir ./ --max-experiments <maxExperiments> --target-runner <targetRunner>

