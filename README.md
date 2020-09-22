## A constraint-based automated instance generation tool ##

This tool is based on the [Essence constraint modelling toolchain](https://constraintmodelling.org/) (Essence-CP) and the automated algorithm configurator [irace](https://iridia.ulb.ac.be/irace/). Starting from an Essence specification of a combinatorial problem, the tool can generate:

- *graded instances* for a single solver: valid, satisfiable and non-trivial instances
	+ valid: parameters of an instances must satisfy validity constraints. They constraints are specified in the problem Essence specification using `where` statements. 
	+ satisfiable: optional, users can also choose to have unsat instances or both
	+ non-trivial: solvable by the considered solver in no less than *n* seconds.
	
- *discriminating instances* between two solvers: valid and satisfiable (optional) instances that are easy for one solver (*favoured solver*) and difficult for the other (*base solver*).

The Essence-CP toolchain used by this tool supports the following solvers:

- minion (CP solver)
- gecode (CP solver)
- chuffed (CP solver)
- glucose (SAT solver)
- glucose-syrup (SAT solver)
- lingeling/plingeling/treengeling (SAT solver)
- cadical (SAT solver)
- minisat (SAT solver)
- bc_minisat_all (AllSAT solver, only works with --number-of-solutions=all)
- nbc_minisat_all (AllSAT solver, only works with --number-of-solutions=all)
- open-wbo (MaxSAT solver, only works with optimisation problems)
- coin-or (MIP solver, *implemented via [MiniZinc](https://www.minizinc.org/)*)
- cplex (MIP solver, *implemented via [MiniZinc](https://www.minizinc.org/)*)
- boolector (SMT solver, supported logics: bv)
- yices (SMT solver, supported logics: bv, lia, idl)
- z3 (SMT solver, supported logics: bv, lia, nia, idl)


### Installation ###

**Install irace**:

Detailed instructions can be found in [irace's README](https://iridia.ulb.ac.be/irace/README.html). Below is a summary of the steps for Linux/macOS:
- Prequisite: [R](https://www.r-project.org/)
- Install [irace](https://iridia.ulb.ac.be/irace/) and its dependency from CRAN:
```
$ R
R> install.packages(c("R6","irace"))
```
- Get the directory where irace was installed using the following command
```
Rscript -e "system.file(package='irace')"
```
- Add the following lines to your `~/.profile` (replace `<IRACE_DIR>` with irace's installation folder)
```
export PATH=<IRACE_DIR>/bin:$PATH 
```

**Install MiniZinc**

- Download and install [MiniZinc](https://www.minizinc.org/)

- Add the following lines to your `~/.profile` (replace `<MZN_DIR>` with the path to MiniZinc's home folder)
```
export PATH=<MZN_DIR>/bin:$PATH
export LD_LIBRARY_PATH=<MZN_DIR>/bin/lib:$LD_LIBRARY_PATH
```

**Install Essence-CP toolchain**

- The toolchain includes  [conjure](https://github.com/conjure-cp/conjure) (an automated constraint modelling tool operating on Essence level), [Savile Row](https://savilerow.cs.st-andrews.ac.uk/) (a modelling assistant tool working on Essence Prime level) and [minion]() (a CP solver). The binaries used for this tool (Linux/MacOS) are included in `bin/Essence-CP` folder.

- Add the following lines to your `~/.profile` (replace <ESSENCE_CP_DIR> with the folder corresponding to your OS):
```
export PATH=<ESSENCE_CP_DIR>:<ESSENCE_CP_DIR>/savilerow:<ESSENCE_CP_DIR>/savilerow/bin:$PATH
```

**Install CPLEX**

- Download and install [IBM ILOG CPLEX](https://www.ibm.com/products/ilog-cplex-optimization-studio)

- Add the following lines to your `~/.profile` (replace `<CPLEX_DIR>` with CPLEX's home folder):
```
export PATH=<CPLEX_DIR>/cplex/bin/<OS>:$PATH
```

### Generating instances ###

**Step 1: setup the experiment**

- Use the Python script `scripts/setup.py` to setup an instance generation experiment. There are three required arguments for the script:

	+ `--runDir <folder_path>`: the folder where the experiment will be run
	+ `--modelFile <file_path>`: path to an Essence specification of your problem. See `examples/essence-models/` for example models.
	+ `--experimentType <type>`: the types of the generated instances. Values: `graded` or `discriminating`
	+ `--evaluationSettingFile`: a `.json` file specifying how to evaluate an instance. Format depends on `experimentType`. See:
		* `examples/evaluation-setting/graded.json`: example for graded instance settings (single solver).
		* `examples/evaluation-setting/discriminating.json`: example for discriminating instance settings (two solvers)
	
	For other arguments (e.g., numer of cores to run in parallel,  number of experiment evaluations, etc), use `python scripts/setup.py --help` for more information
		
- Example 1: setup an experiment with a single core and default tuning budget (5000 evaluations)
```
mkdir cvrp-experiment
python scripts/setup.py --runDir cvrp-experiment --modelFile examples/essence-models/cvrp.essence --experimentType discriminating --evaluationSettingFile examples/evaluation-setting/discriminating.json
```
- Example 2: setup an experiment with 5 cores and smaller tuning budget
```
mkdir cvrp-experiment
python scripts/setup.py --runDir cvrp-experiment --modelFile examples/essence-models/cvrp.essence --experimentType discriminating --evaluationSettingFile examples/evaluation-setting/discriminating.json --nCores 5 --maxExperiments 1000
```

**Step 2: start the tuning experiment**

- Go to your `runDir` folder and run the script `run.sh`: this will start the tuning experiment to search for instances. This can take a long time. You can use parallelisation to speed it up (see other arguments in step 1).

- If the tuning is stopped prematurely, e.g., it is killed by user during its run, or a solver run is crashed, you can resume the tuning by calling the `run.sh` script again. This will continue the tuning from the last successful point.

**Step 3: collect results**

- When the tuning is finished (or even when it is still running!), you can use the Python script `scripts/collect-results.py` to:
	+ get a summary of results (as a `.csv` file) 
	+ copy graded/discriminating instances into a specific folder.
	+ Example: `python scripts/collect-results.py --runDir cvrp-experiment --copyInstancesTo cvrp-experiment/dis-instances/`

- During the tuning (step 2), there are several temporary files generated and saved in `<runDir>/detailed-output/` folder. They were used for
	+ saving detailed output so the tuning can be resumed if needed.
	+ saving all generated instances (including non-graded & non-discriminating instances).
	+ saving temporary solving output to avoid re-translating each generator instance multiple times. 
These files can be quite memory-heavy. They can be removed once the tuning is finished and results were collected.

### Papers ###

- Akgün, Dang, Miguel, Salamon, Spracklen, and Stone. Instance generation via generator instances. *CP 2019* ([pdf](https://research-repository.st-andrews.ac.uk/bitstream/handle/10023/18669/crc.pdf?sequence=1&isAllowed=y))

- Akgün, Dang, Miguel, Salamon, Spracklen, and Stone. Discriminating Instance Generation from Abstract Specifications: A Case Study with CP and MIP. *CPAIOR 202*0 ([link](https://link.springer.com/chapter/10.1007/978-3-030-58942-4_3))
