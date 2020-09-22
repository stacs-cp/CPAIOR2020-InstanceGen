#!/usr/bin/env python

# wrapper for irace call to a run for generating instances from Conjure specification
# syntax: python wrapper.py <iraceConfigurationId> <1> <randomSeed> <dummyName> <configurationValues>
# output: the last stdout line is the score returned to irace 

import os
import sys
import subprocess
import random
import time
import glob
import shlex
import re
import json
from shutil import move
import datetime
from shutil import copyfile
import numpy as np

detailedOutputDir = './detailed-output'

solverInfo = {}
solverInfo['cplex'] = {'timelimitUnit': 'ms', 
                            'timelimitPrefix': '--time-limit ',
                            'randomSeedPrefix': 'via text file'}
solverInfo['chuffed'] = {'timelimitUnit': 'ms',
                            'timelimitPrefix': '-t ',
                            'randomSeedPrefix': '--rnd-seed '}
solverInfo['minion'] = {'timelimitUnit': 's',
                            'timelimitPrefix': '-timelimit ',
                            'randomSeedPrefix': '-randomseed '}
solverInfo['gecode'] = {'timelimitUnit': 'ms',
                            'timelimitPrefix': '-time ',
                            'randomSeedPrefix': '-r '}
solverInfo['glucose'] = {'timelimitUnit': 's',
                            'timelimitPrefix': '-cpu-lim=',
                            'randomSeedPrefix': '-rnd-seed='}
solverInfo['glucose-syrup'] = {'timelimitUnit': 's',
                            'timelimitPrefix': '-cpu-lim=',
                            'randomSeedPrefix': '-rnd-seed='}
solverInfo['lingeling'] = {'timelimitUnit': 's',
                            'timelimitPrefix': '-T ',
                            'randomSeedPrefix': '--seed '}
solverInfo['cadical'] = {'timelimitUnit': 's',
                            'timelimitPrefix': '-t ',
                            'randomSeedPrefix': '--seed='}
solverInfo['open-wbo'] = {'timelimitUnit': 's',
                            'timelimitPrefix': '-cpu-lim=',
                            'randomSeedPrefix': '-rnd-seed='}
solverInfo['boolector'] = {'timelimitUnit': 's',
                            'timelimitPrefix': '--time=',
                            'randomSeedPrefix': '--seed='}


def log(logMessage):
    print("{0}: {1}".format(datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'), logMessage))


def read_file(fn):
    lsLines = []
    with open(fn,'rt') as f:
        lsLines = [line.rstrip('\n') for line in f]
        
    return lsLines


def search_string(s, lsStrs):
    lsOut = []
    for line in lsStrs:
        if s in line:
            lsOut.append(line)
    return lsOut



def run_cmd(cmd,outFile=None):
    lsCmds = shlex.split(cmd)
    p = subprocess.run(lsCmds,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    output = p.stdout.decode('utf-8')
    if outFile is not None:
        with open(outFile,'wt') as f:
            f.write(output)
    return output, p.returncode




def deleteFile(fn):
    if isinstance(fn,list): # delete a list of files
        for name in fn:
            if isinstance(name,list):
                deleteFile(name)
            elif os.path.isfile(name):
                os.remove(name)
    else: # delete by pattern
        lsFile = glob.glob(fn)
        for fn in lsFile:
            os.remove(fn)


def conjure_translate_parameter(eprimeModelFile, paramFile, eprimeParamFile):
    cmd = 'conjure translate-parameter ' + '--eprime=' + eprimeModelFile + ' --essence-param=' + paramFile + ' --eprime-param=' + eprimeParamFile
    log(cmd)
    cmdOutput, returnCode = run_cmd(cmd)

    if returnCode != 0:
        raise Exception(cmdOutput)


def savilerow_translate(auxFile, eprimeModelFile, eprimeParamFile, minionFile, timelimit, flags):
    cmd = 'savilerow ' + eprimeModelFile + ' ' + eprimeParamFile + ' -out-aux ' + auxFile + ' -out-minion ' + minionFile + ' -save-symbols '  + '-timelimit ' + str(timelimit) + ' ' + flags
    log(cmd)

    start = time.time() 
    cmdOutput, returnCode = run_cmd(cmd)
    SRTime = time.time() - start

    status = 'SRok'
    # if returnCode !=0, check if it is because SR is out of memory or timeout
    if ('GC overhead limit exceeded' in cmdOutput) or ('OutOfMemoryError' in cmdOutput) or ('insufficient memory' in cmdOutput):
        status = 'SRMemOut'
    elif 'Savile Row timed out' in cmdOutput:
        status = 'SRTimeOut'
    # if returnCode != 0 and its not due to a timeout or memory issue raise exception to highlight issue
    elif returnCode != 0:
        raise Exception(cmdOutput)

    return status, SRTime


def savilerow_parse_solution(eprimeModelFile, minionSolFile, auxFile, eprimeSolFile):
    #command syntax: savilerow generator.eprime -mode ReadSolution -out-aux output.aux -out-solution sol.test -minion-sol-file test.txt
    cmd = 'savilerow ' + eprimeModelFile + ' -mode ReadSolution -out-aux ' + auxFile + ' -out-solution ' + eprimeSolFile + ' -minion-sol-file ' + minionSolFile
    cmdOutput, returnCode = run_cmd(cmd)

    log(cmd)
    if returnCode != 0:
        raise Exception(cmdOutput)


def conjure_translate_solution(eprimeModelFile, paramFile, eprimeSolFile, essenceSolFile):
    cmd = 'conjure translate-solution --eprime=' + eprimeModelFile + ' --essence-param=' + paramFile  + ' --eprime-solution=' + eprimeSolFile + ' --essence-solution ' + essenceSolFile
    log(cmd)

    cmdOutput, returnCode = run_cmd(cmd)

    if returnCode != 0:
        raise Exception(cmdOutput)


def run_minion(minionFile, minionSolFile, seed, timelimit, flags):
    cmd = 'minion ' + minionFile + ' -solsout ' + minionSolFile + ' -randomseed ' + str(seed) + ' -timelimit ' + str(timelimit) + ' ' + flags
    log(cmd)

    start = time.time()
    cmdOutput, returnCode = run_cmd(cmd)
    runTime = time.time() - start

    # check if minion is timeout or memout
    status = None
    if 'Time out.' in cmdOutput:
        status = 'solverTimeOut'
    elif ('Error: maximum memory exceeded' in cmdOutput) or ('Out of memory' in cmdOutput) or ('Memory exhausted!' in cmdOutput):
        status = 'solverMemOut'
    else:
        if 'Solutions Found: 0' in cmdOutput:
            status = 'unsat'
        else:
            status = 'sat'

    if returnCode != 0:
        raise Exception(cmdOutput)

    return status, runTime


def read_minion_variables(minionFileSections):
    search_section = minionFileSections['SEARCH']
    for line in search_section:
        if "PRINT" in line:
            variables = line.split("PRINT")[1]
            variables = variables.replace("[","").replace("]","")
            return variables

    raise Exception("Cant find minion ordered variables section")


def parse_minion_file(minionFile):
    minionFileSections= {}
    lines = []
    file = open(minionFile, 'r')
    current_section = None
    for line in file:
        if "**" in line:
            if current_section is not None:
                if line.strip()[0]!='*': # in case the section header is on the same line with the last line of the previous section's content
                    s = line[:line.find('*')]
                    lines.append(s)
                if current_section in minionFileSections:
                    minionFileSections[current_section].extend(lines)
                else:
                    minionFileSections[current_section] = lines
            current_section = line.replace("*", "").strip()
            lines = []
            continue

        lines.append(line)

    file.close() 
    return minionFileSections


def parse_minion_solution(minionSolFile):
    with open(minionSolFile) as solFile:
        return solFile.read().strip()


def write_out_modified_minion_file(minionFile, minionFileSections):
    file = open(minionFile, 'w')
    minionSectionKeys = ['VARIABLES','SEARCH', 'TUPLELIST', 'CONSTRAINTS']
    file.write("MINION 3\n")
    for key in minionSectionKeys:
        file.write("**{0}**".format(key) + "\n")
        for value in minionFileSections[key]:
            file.write(value.strip() + "\n")

    file.write("**EOF**")
    file.close()


def encode_negative_table(minionFile, minionSolString):
    minionFileSections = parse_minion_file(minionFile)

    variables = read_minion_variables(minionFileSections)

    #Grab the tuple list from the parsed minion section if it exists
    tuple_list = minionFileSections.get('TUPLELIST', [])

    #If the tuple_list is empty this must be the first time running this minion file. Add the negativetable constraint
    if len(tuple_list) == 0:
        minionFileSections['CONSTRAINTS'].append('negativetable([' + variables+ '],negativeSol)')
    #otherwise, remove the first line (negativeSol ...)
    else:
        tuple_list = tuple_list[1:]
    
    # only update minionFile if minion finds a solution, i.e., a new instance is generated
    if minionSolString != '':
        tuple_list.append(minionSolString)
        minionFileSections['TUPLELIST'] = ["negativeSol {0} {1}".format(len(tuple_list), len(variables.split(",")))]
        minionFileSections['TUPLELIST'].extend(tuple_list)
        write_out_modified_minion_file(minionFile, minionFileSections)


def make_conjure_solve_command(essenceModelFile, eprimeModelFile, instFile, solver, SRTimelimit=0, SRFlags='', solverTimelimit=0, solverFlags='', seed=None):
    # temporary files that will be removed
    lsTempFiles = []

    # SROptions string
    SROptionsStr = ''
    if SRTimelimit>0:
        SROptionsStr += '-timelimit ' + str(int(SRTimelimit*1000))
    SROptionsStr += ' ' + SRFlags

    # solverInfo string
    solverOptionStr = ""

    # solver timelimit
    if not solver in solverInfo:
        raise Exception("Sorry, solver " + solver + " is not yet supported.")
    opts = solverInfo[solver]
    if solverTimelimit > 0:
        if opts['timelimitUnit'] == 's':
            solverTimelimit = int(solverTimelimit)
        elif opts['timelimitUnit'] == 'ms':
            solverTimelimit = int(solverTimelimit * 1000)
        else:
            raise Exception("ERROR: solver " + solver + ": timelimitUnit " + opts['timelimitUnit'] + " not supported")
        solverOptionStr += opts['timelimitPrefix'] + str(solverTimelimit)

    # solver random seed (only when the solver supports passing a random seed, i.e., solverInfo['randomSeedPrefix'] != None
    if (seed != None) and (opts['randomSeedPrefix'] != None):
        if solver == 'cplex': # cplex case is special: we need to create a temporary text file to pass the random seed to cplex            
            rndSeedCplexFile = instFile + '.cplexseed'
            with open(rndSeedCplexFile,'wt') as f:
                f.write('CPXPARAM_RandomSeed ' + str(seed))
            lsTempFiles.append(rndSeedCplexFile)
            solverOptionStr += ' --readParam ' + rndSeedCplexFile
        else:
            solverOptionStr += ' ' + opts['randomSeedPrefix'] + str(seed)

    # solver flags
    solverOptionStr += ' ' + solverFlags

    # conjure solve command
    outDir = os.path.dirname(eprimeModelFile)
    eprimeModelFile = os.path.basename(eprimeModelFile)
    conjureCmd = 'conjure solve ' + essenceModelFile + ' ' + instFile \
                + ' -o ' + outDir + ' --use-existing-models=' + eprimeModelFile \
                + ' --savilerow-options "' + SROptionsStr + '"' \
                + ' --solver-options "' + solverOptionStr + '"' \
                + ' --solver=' + solver

    return conjureCmd, lsTempFiles
    

def call_conjure_solve(essenceModelFile, eprimeModelFile, instFile, setting, seed):
    solver = setting['name']
    lsTempFiles = []

    # make conjure solve command line
    conjureCmd, tempFiles = make_conjure_solve_command(essenceModelFile, eprimeModelFile, instFile, solver, setting['SRTimelimit'], setting['SRFlags'], setting['solverTimelimit'], setting['solverFlags'], seed)
    lsTempFiles.extend(tempFiles)

    # call conjure
    print("\nCalling conjure")
    log(conjureCmd)
    cmdOutput, returnCode = run_cmd(conjureCmd)
    log(cmdOutput)

    status = None
    if ('GC overhead limit exceeded' in cmdOutput) or ('OutOfMemoryError' in cmdOutput) or ('insufficient memory' in cmdOutput):
        status = 'SRMemOut'
    elif 'Savile Row timed out' in cmdOutput:
        status = 'SRTimeOut'
    elif 'increase MAX_VARS' in cmdOutput:  # what are we checking here???
        status = 'SRMemOut'
    elif ('Error: maximum memory exceeded' in cmdOutput) or ('Out of memory' in cmdOutput) or ('Memory exhausted!' in cmdOutput):
        status = 'solverMemOut'
    elif returnCode != 0:
        raise Exception(cmdOutput)

    baseFile = eprimeModelFile.replace('.eprime','') + '-' + os.path.basename(instFile).replace('.param','')
    infoFile = baseFile + '.eprime-info'
    inforFile = baseFile + '.eprime-infor'
    minionFile = baseFile + '.eprime-minion'
    dimacsFile = baseFile + '.eprime-dimacs'
    fznFile = baseFile + '.eprime-param.fzn'
    mznFile = baseFile + '.eprime.mzn'
    eprimeParamFile = baseFile + '.eprime-param'
    eprimeSolutionFile = glob.glob(baseFile + '*.eprime-solution')
    solutionFile = glob.glob(baseFile + '*.solution')
    solutionFile.extend(glob.glob(os.path.basename(baseFile) + '.solution')) # in case conjure doesn't generate essence solution file within the folder of eprime model
    lsTempFiles.extend([inforFile, minionFile, dimacsFile, mznFile, fznFile, eprimeParamFile, eprimeSolutionFile, solutionFile])

    print("Waiting for " + infoFile)

    # Wait a maximum of 60s for SR-info file to appear 
    if status != 'SRMemOut':
        max_wait = 60
        while True:
            if os.path.isfile(infoFile):
                break
            elif max_wait <= 0:
                os.stat(infoFile)
                raise Exception("Waited max time for SR-info file to appear {0}".format(infoFile))
            else:
                time.sleep(1)
                max_wait -= 1

    if os.path.isfile(infoFile):
        # rename infoFile so that it includes random seed and solver name
        newInfoFile = baseFile + '-seed_' + str(seed) + '-' + solver + '.eprime-info'
        print("Renaming SR info file: " + infoFile + " -> " + newInfoFile)
        if os.path.isfile(infoFile):
            os.rename(infoFile, newInfoFile)
        infoFile = newInfoFile
    
        # parse SR info file
        status, SRTime, solverTime = parse_SR_info_file(infoFile, timelimit=setting['solverTimelimit'])

    deleteFile(lsTempFiles)
    return status, SRTime, solverTime


def parse_SR_info_file(fn, knownSolverMemOut=False, timelimit=0): 
    lsLines = read_file(fn)
   
    def get_val(field):
        ls = search_string(field, lsLines)
        if len(ls)>0:
            return ls[0].split(':')[1].strip()
        else:
            return None
    
    # initial assumptions
    SRTime = 0
    solverTime = 0
    status = None

    # SR status
    if get_val('SavileRowTimeOut') == "1" or get_val('SavileRowClauseOut')==1:
        status = "SRTimeOut"
    
    # SR time and solver time
    if get_val('SavileRowTotalTime') != None:
        SRTime = float(get_val('SavileRowTotalTime'))
    if get_val('SolverTotalTime') != None:
        solverTime = float(get_val('SolverTotalTime'))

    # solver status
    if status != "SRTimeOut":

        # if solver is out of memory because of runsolver, SR will write an info file with solverTimeOut=1. We'll fix it and return.
        if knownSolverMemOut:
            status = 'solverMemOut'
            return status, SRTime, solverTime

        if get_val('SolverMemOut') == "1":
            status = 'solverMemOut'
        elif get_val('SolverTimeOut') == "1":
            status = 'solverTimeOut'
        elif get_val('SolverNodeOut') == "1":
            status = 'solverNodeOut'
        else:
            if timelimit>0 and solverTime>timelimit: # for the case when solver timeout but SR reports SolverTimeOut=0 (happens with minizinc atm)
                status = 'solverTimeOut'
            elif get_val('SolverSatisfiable') == "1":
                status = 'sat'
            else:
                status = 'unsat'
    return status, SRTime, solverTime


def run_single_solver(instFile, seed, setting):
    essenceModelFile = detailedOutputDir + '/problem.essence'
    eprimeModelFile = detailedOutputDir + '/problem.eprime'
    instance = os.path.basename(instFile).replace('.param','')

    score = None
    print('\n')
    log("Solving " + instFile + '...')

    solverSetting = setting['solver']

    for i in range(setting['nEvaluations']):
        rndSeed = seed + i
        print("\n\n----------- With random seed " + str(i) + 'th (' + str(rndSeed) + ')')
        runStatus, SRTime, solverTime = call_conjure_solve(essenceModelFile, eprimeModelFile, instFile, solverSetting, rndSeed)

        # print out results
        log("\nRun results: solverType=" + solver + ', solver=' + solverSetting['name'] + ', instance=' + instance + ', runId=' + str(i) \
                    + ', '.join([s + '=' + str(localVars[s]) for s in ['runStatus','SRTime','solverTime']])) 
        
        # make score
        if instanceOptions['scoringScheme'] == 'cp2019':
            # if the instance violates one of the criteria on at least one of the seeds, make score and quit
            if SRMemOut==1 or SRTimeOut==1 or solverMemOut==1 or solverTimeOut==1 or solverNodeOut==1 or sat=='no':
                score = 0
            # if the instance is too easy, also make score and quit
            elif instanceOptions['solverMinNode']>0 and nNodes<instanceOptions['solverMinNode']:
                score = -nNodes
            elif instanceOptions['solverMinTime']>0 and solverTime<instanceOptions['solverMinTime']:
                score = -solverTime
            if score is not None:
                break
        elif instanceOptions['scoringScheme'] == 'new-01':
            if score is None: # initialise score for the first run
                score = 0
            if ((sat=='no' and (not 'unsat' in instanceOptions['gradedTypes']))
                or (sat=='yes' and (not 'sat' in instanceOptions['gradedTypes']))): # if the instance type is unwanted, mark all remaining runs as that type and stop the evaluation
                score += 0
                lsOutputLines.extend([output]*(instanceOptions['nEvaluations']-i-1)) # mark all remaining runs as the same type
                break            
            # if the instance violates one of the criteria, give a score of 0
            if SRMemOut==1 or SRTimeOut==1 or solverMemOut==1 or solverTimeOut==1 or solverNodeOut==1:
                score += 0
                continue
            # if the instance is too easy, give it a score of -solverTime (or -solverNode)
            if instanceOptions['solverMinNode']>0 and nNodes<instanceOptions['solverMinNode']:
                score += -nNodes
            elif instanceOptions['solverMinTime']>0 and solverTime<instanceOptions['solverMinTime']:
                score += -solverTime
            # if the instance is graded, give it a score of nEvaluations * -minSolverTime (or -minSolverNode)
            else:
                if instanceOptions['solverMinNode']>0:
                    score += instanceOptions['nEvaluations'] * (-instanceOptions['solverMinNode'])
                else:                    
                    score += instanceOptions['nEvaluations'] * (-instanceOptions['solverMinTime'])
        elif instanceOptions['scoringScheme'] == 'new-02':
            if score is None: # initialise score for the first run
                score = 0
            # if the instance violates one of the criteria, give a score of 0
            if SRMemOut==1 or SRTimeOut==1 or solverMemOut==1 or solverTimeOut==1 or solverNodeOut==1:
                score += 0
                continue
            # if the instance is sat/unsat+too easy, give it a score of -solverTime (or -solverNode)
            if instanceOptions['solverMinNode']>0 and nNodes<instanceOptions['solverMinNode']:
                score += -nNodes
            elif instanceOptions['solverMinTime']>0 and solverTime<instanceOptions['solverMinTime']:
                score += -solverTime
            # if the instance is unsat+graded, give it a score of -minSolverTime
            elif sat=='no':
                if instanceOptions['solverMinNode']>0:
                    score += -instanceOptions['solverMinNode']
                else:
                    score += -instanceOptions['solverMinTime']
            # if the instance is sat+graded, give it a score of nEvaluations * -minSolverTime (or -minSolverNode)
            else:
                if instanceOptions['solverMinNode']>0:
                    score += instanceOptions['nEvaluations'] * (-instanceOptions['solverMinNode'])
                else:                    
                    score += instanceOptions['nEvaluations'] * (-instanceOptions['solverMinTime'])        
        else:
            raise Exception("ERROR: scoring scheme " + instanceOptions['scoringScheme'] + " is not supported")


    # make final score
    if (instanceOptions['scoringScheme'] == 'cp2019') and (score is None):
        # i.e., instance satisfies our criteria on all seeds
        if instanceOptions['solverMinNode']>0:
            score = -instanceOptions['solverMinNode']
        else:
            score = -instanceOptions['solverMinTime']    
    elif instanceOptions['scoringScheme'] in ['new-01', 'new-02']:
        # do nothing
        score = score
    else:
        raise Exception("ERROR: scoring scheme " + instanceOptions['scoringScheme'] + " is not supported")

    return outHeader, lsOutputLines, score, lsTempOutFiles


def read_args(args):
    #### read arguments (following irace's wrapper input format) ###
    k = 1
    configurationId = int(args[k])
    k = k + 2 # skip second argument (<1>) 
    seed = int(args[k])
    k = k + 2 # skip 4th argument (dummy instance name)
    params = args[k:]
    paramDict = {} # generator parameter values suggested by irace
    for i in range(0,len(params),2):
        paramDict[params[i][1:]] = params[i+1]

    log(' '.join(args))

    # update param values of log-transformed params, since irace doesn't support non-positive values for those params
    metaFile = None
    if os.path.isfile('./params.irace.meta'):
        metaFile = './params.irace.meta'
    if metaFile is not None:
        with open(metaFile,'rt') as f:
            lsMeta = f.readlines()
        for ln in lsMeta:
            ln = ln[0:-1]
            param = ln.split(' ')[0]
            delta = int(ln.split(' ')[1])
            paramDict[param] = str(int(paramDict[param]) - delta)

    return configurationId, seed, paramDict


def read_setting(settingFile):
    if os.path.isfile(settingFile) is False:
        print("ERROR: setting file " + settingFile + " is missing.")
        sys.exit(1)
    with open(settingFile) as f:
        setting = json.load(f)
    return setting


def solve_generator(configurationId, paramDict, setting, seed):
    ### create a new instance by solving a generator instance ###
    # we need to make sure that we don't create an instance more than once from the same generator instance
    # this is done by generating the minion instance file only once, and everytime a new solution is created, it'll be added to a negative table in the minion file
    # NOTE 1: we save the generated minion file because we want to save SR time next time the same configuration is run by irace. However, this increases the storage memory used during the tuning, as those minion files can be huge!
    # NOTE 2: the generated solution will only added to the minion file at the end of a wrapper run (when the corresponding problem instance is successfully taken by the considered target solvers) by calling function save_generator_solution. This is to make sure that if a run is unsuccessful and terminated, the same instance will be generated when the tuning is resumed.

    # write generator instance to an essence instance file
    paramFile = detailedOutputDir + '/gen-inst-' + str(configurationId) + '.param'
    print('\n')
    log("Creating generator instance: " + paramFile) 
    lsLines = ['letting ' + key + ' be ' + str(val) for key, val in paramDict.items()]
    with open(paramFile, 'wt') as f:
        f.write('\n'.join(lsLines))
    
    # files used/generated during the solving process
    eprimeModelFile = detailedOutputDir + "/generator.eprime"
    baseFileName = paramFile.replace('.param','')
    minionFile = baseFileName + '.minion' # minion input file, including a negative table saving previously generated solutions of the same generator instance
    minionSolFile = baseFileName + '.solution' # solution file generated by minion, will be removed afterwards
    auxFile = baseFileName + '.aux' # aux file generated by SR, will be kept so we don't have to re-generate it next time solving the same generator instance
    eprimeSolFile =  baseFileName + '.solution.eprime-param' # eprime solution file created by SR, will be removed afterwards
    essenceSolFile = baseFileName + '.solution.param' # essence solution file created by conjure, will be returned as a problem instance
    minionSolString = '' # content of minion solution file, to be added to minion negative table in minionFile
    
    # status of the solving
    genStatus = None # SRTimeOut/SRMemOut/solverTimeOut/solverMemOut/sat/unsat

    # if the generator instance is solved for the first time
    if (not os.path.exists(minionFile)) or (os.stat(minionFile).st_size == 0):
        eprimeParamFile = baseFileName + '.eprime-param'
        conjure_translate_parameter(eprimeModelFile, paramFile, eprimeParamFile) # translate generator instance from Essence to Essence Prime
        genStatus, genSRTime = savilerow_translate(auxFile, eprimeModelFile, eprimeParamFile, minionFile, setting['genSRTimelimit']*1000, setting['genSRFlags']) # translate generator instance from Essence Prime to minion input format
        os.remove(eprimeParamFile)
    else:
        genStatus = 'SRok'
        genSRTime = 0

    # start solving it
    if genStatus == 'SRok':
        genStatus, genSolverTime = run_minion(minionFile, minionSolFile, seed, setting['genSolverTimelimit'], setting['genSolverFlags'])
        if genStatus == 'sat':
            minionSolString = parse_minion_solution(minionSolFile)
            savilerow_parse_solution(eprimeModelFile, minionSolFile, auxFile, eprimeSolFile) # parse solution from minion to Essence Prime
            conjure_translate_solution(eprimeModelFile, paramFile, eprimeSolFile, essenceSolFile) # parse solution from Essence Prime to Essence
        deleteFile([minionSolFile,eprimeSolFile]) # delete minionSolFile after used, otherwise the negativetable will have duplicated items. eprimeSolFile is removed to make sure that in the next runs, if no solution is found by minion, no Essence solution file is created
    else:
        genSolverTime = 0

    # print out results of the generator solving process
    localVars = locals()
    print('\n')
    log("\nGenerator results: genInstance=" + os.path.basename(paramFile).replace('.param','') + ', ' + ', '.join([name + '=' + str(localVars[name]) for name in ['genStatus','genSRTime','genSolverTime']]))
    
    return genStatus, essenceSolFile, minionFile, minionSolString


def run_discriminating_solvers(instFile, seed, setting): 
    ### evaluate a generated instance based on discriminating power with two solvers ###
    # NOTE: 
    # - this function can be improved using parallelisation, as there are various cases in the scoring where runs can be safely terminated before they finished. Things to consider
    #       + gnu-parallel for implementation
    #       + runsolver for safely terminating a solver run
    
    # scoring scheme for discriminating solvers:
    # - gen unsat/SR memout/SR timeout: Inf
    # - gen solver timeout: 2
    # - inst unwanted type or SR timeout (either solver): 1 (ISSUE: with this new implementation, we can't recognise SR timeout, so we treat it as both solver timeout, i.e., score=0)
    # - favoured solver timeout (any run) or base solver too easy (any run): 0
    # - otherwise: max{-minRatio, -baseSolver/favouredSolver}
    # - note: if minRatio>0, ideally we should set timelimit_baseSolver = minRatio * timelimit_favouredSolver

    essenceModelFile = './problem.essence'
    eprimeModelFile = detailedOutputDir + '/problem.eprime'
    instance = os.path.basename(instFile).replace('.param','')
    
    score = None
    print('\n')
    log("Solving " + instFile + '...')

    # solve the instance using each solver
    stop = False  # when to stop the evaluation early
    lsSolvingTime = {}  # solving time of each solver per random seed
    lsSolvingTime['favouredSolver'] = []
    lsSolvingTime['baseSolver'] = []
    for i in range(setting['nEvaluations']):
        rndSeed = seed + i   
               
        status = 'ok'
        for solver in ['favouredSolver','baseSolver']:
            solverSetting = setting[solver]
            print("\n\n---- With random seed " + str(i) + 'th (' + str(rndSeed) + ') and solver ' + solverSetting['name'] + ' (' + solver + ')')
            
            runStatus, SRTime, solverTime = call_conjure_solve(essenceModelFile, eprimeModelFile, instFile, solverSetting, rndSeed)
            localVars = locals()
            log("\nRun results: solverType=" + solver + ', solver=' + solverSetting['name'] + ', instance=' + instance + ', runId=' + str(i) + ', '\
                    + ', '.join([s + '=' + str(localVars[s]) for s in ['runStatus','SRTime','solverTime']]))
            
            lsSolvingTime[solver].append(solverTime)
            
            #------------ update score
            # inst unwanted type: score=1
            if (setting['gradedTypes']!='both') and (runStatus in ['sat','unsat']) and (runStatus!=setting['gradedTypes']):
                print("\nunwanted instance type. Quitting!...")
                score = 1
                stop = True
                status = 'unwantedType'
                break
            # SR timeout or SR memout: score=1
            if runStatus in ['SRTimeOut','SRMemOut']:
                print("\nSR timeout/memout while translating the instance. Quitting!...")
                score = 1
                stop = True
                status = runStatus
                break
            # favoured solver timeout (any run) or base solver too easy (any run): score=0
            if (solver=='favouredSolver') and (runStatus=='solverTimeOut'):
                print("\nfavoured solver timeout. Quitting!...")
                score = 0
                stop = True
                status = 'favouredTimeOut'
                break
            if (solver=='baseSolver') and (solverTime<solverSetting['solverMinTime']):
                print("\ntoo easy run for base solver. Quitting!...")
                score = 0
                stop = True
                status = 'baseTooEasy'
                break


        # evaluation is stopped as there's no need to test the rest
        if stop:
            break
                    
    # if nothing is stop prematurely, calculate mean solving time & ratio, and update score
    ratio = 0
    if stop is False:
        meanSolverTime_favouredSolver = np.mean(lsSolvingTime['favouredSolver'])
        meanSolverTime_baseSolver = np.mean(lsSolvingTime['baseSolver'])
        ratio = meanSolverTime_baseSolver / meanSolverTime_favouredSolver
        # if minRatio is provided, use it
        if setting['minRatio'] != 0:
            score = max(-setting['minValue'], -ratio)
        else: # otherwise, simply use the current ratio
            score = -ratio
            
        print('\n\nMean solving time: ')
        print('\t- Favoured solver: ' + str(np.round(meanSolverTime_favouredSolver,2)) + 's')
        print('\t- Base solver: ' + str(np.round(meanSolverTime_baseSolver,2)) + 's')
        print('\t- Ratio: ' + str(np.round(ratio,2)))

    # print summary for later analysis
    favouredSolverTotalTime = baseSolverTotalTime = 0
    if len(lsSolvingTime['favouredSolver'])>0:
        favouredSolverTotalTime = sum(lsSolvingTime['favouredSolver'])
    if len(lsSolvingTime['baseSolver'])>0:
        baseSolverTotalTime = sum(lsSolvingTime['baseSolver'])
    s = "\nInstance summary: instance=" + instance + ', status=' + status + ', favouredSolverTotalTime=' + str(favouredSolverTotalTime) + ', baseSolverTotalTime=' + str(baseSolverTotalTime) + ', ratio=' + str(ratio)
    print(s)
    
    return score


def print_score(startTime, score):
    # print summary results and the score (i.e., feedback to irace)
    totalWrapperTime = time.time() - startTime
    print("\nTotal wrapper time: " + str(totalWrapperTime))
    print("\nTuning results: ")
    print(str(score) + ' ' + str(np.round(totalWrapperTime,2)))


def main():
    startTime = time.time()

    # parse arguments
    configurationId, seed, paramDict = read_args(sys.argv)

    # set random seed
    random.seed(seed)

    # read all setting
    setting = read_setting('./setting.json')

    # solve the generator problem
    genStatus, genSolFile, genMinionFile, genMinionSolString = solve_generator(configurationId, paramDict, setting['generatorSettings'], seed)

    # if no instance is generated, return immediately
    if genStatus != 'sat':
        print('No instance file generated. Exitting...')
        # determine the score
        if genStatus != 'solverTimeOut':
            score = 'Inf' # if the generator configuration is unsat/SRTimeOut/SRMemOut/solverMemOut, return "Inf", so that irace will discard this configuration immediately
        else:
            score = 2 # if the generator configuration is unsolved because minion timeout, penalise it heavier than any other cases where the generator configuration is sat
        # print out score and exit
        print_score(startTime, score)
        return
    
    # if an instance is generated, move on and evaluate it
    instFile = detailedOutputDir + '/inst-' + str(configurationId) + '-' + str(seed) + '.param'
    move(genSolFile, instFile)

    experimentType = setting['generalSettings']['experimentType']

    # evaluate the generated instance based on gradedness (single solver)
    if experimentType == 'graded':
        print("TODO")

    # evaluate the generated instance based on discriminating power (two solvers)
    elif experimentType == 'discriminating':
        score = run_discriminating_solvers(instFile, seed, setting['evaluationSettings'])

    else:
        raise Exception("ERROR: invalid experimentType: " + experimentType)

    # add the generated instance into generator's minion negative table, so that next time when we solve this generator instance again we don't re-generate the same instance
    encode_negative_table(genMinionFile, genMinionSolString)

    # print out score and exit
    print_score(startTime, score)


main()

# scoring scheme new-01
# - gen unsat: Inf
# - gen SR/minion timeout: 2
# - if a generator instance is:
#    + unsat: score=Inf (the configuration is rejected immediately by irace)
#    + SR/minion timeout: score=2 (instead of 1, to match with the discriminating scheme)
# - if a generator instance is sat, i.e., an instance is generated:
#    + score for each of 5 runs: SR timeout = unwantedType = solverTimeout = 0, too easy = -solverTime, graded = nSeeds * -minSolverTime
#      and we just sum them up, with the exception that, as soon as one of the 5 runs is unwantedType, the remaining seeds will be marked as unwantedType too, so we don't actually run them (just duplicate the unwantedType results for the remaining seeds)

# scoring scheme for discriminating solvers:
# - gen unsat: Inf
# - gen SR/minion timeout: 2
# - inst unwanted type or SR timeout (either solver): 1
# - favoured solver timeout (any run) or base solver too easy (any run): 0
# - otherwise: max{-minRatio, -badSolver/goodSolver}
# - note: timelimit_badSolver = minRatio * timelimit_goodSolver
