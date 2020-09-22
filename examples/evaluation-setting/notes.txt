The evaluation settings for each solver consists of the following fields:
- gradedTypes: types of instances that the user wants to generate. Possible values: "sat", "unsat", "both"
- nEvaluations: the number of runs tested per generated instance
- SRTimelimit: Savile Row time limit when running "conjure solve" to solve a generated instance using the considered solver. Savile Row will refine an instance from Essence Prime level to the input language supported by the solver. 
- SRFlags: extra flags for Savile Row. This includes several preprocessing and optimisation techniques, please see Savile Row documentation for more details (https://savilerow.cs.st-andrews.ac.uk/)
- solverMinTime: minimum time required to solve an instance, this is to avoid having trivial instances for the considered solver.
- solverTimelimit: time limit per instance for the considered solver
- solverFlags: extra flags given to the solver call

Note: All time limit values are in seconds
