#!/usr/bin/env python

import datetime
import os
import sys
import argparse
from shutil import copyfile
from shutil import copy
from shutil import move
import json
import subprocess
import shlex
from collections import OrderedDict

def replace_string(srcStr, destStr, fileName):
    with open(fileName, 'rt') as f:
        lsLines = f.readlines()
        lsLines = [ln.replace(srcStr, destStr) for ln in lsLines]
    with open(fileName, 'wt') as f:
        f.writelines(lsLines)


def log(logMessage):
    print("{0}: {1}".format(datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'), logMessage))


def run_cmd(cmd, printOutput=True):
    log(cmd)
    lsCmds = shlex.split(cmd)
    p = subprocess.run(lsCmds,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    output = p.stdout.decode('utf-8')
    if printOutput:
        print(output)
    if p.returncode!=0:
        sys.exit(1)
    return output


def get_script_path():
    return os.path.dirname(os.path.realpath(sys.argv[0]))


def get_conjure_version():
    ls = run_cmd('conjure --help', printOutput=False).split('\n')
    s = [s for s in ls if 'Repository version' in s][0]
    conjureVersion = s.split(' ')[2]
    return conjureVersion


def get_SR_version():
    ls = run_cmd('savilerow -help', printOutput=False).split('\n')
    s = [s for s in ls if 'Repository Version' in s][0]
    srVersion = s.split(' ')[5]
    return srVersion


def get_minizinc_version():
    ls = run_cmd('minizinc --version', printOutput=False).split('\n')
    ls = [s for s in ls if 'version ' in s]
    if len(ls)>0:
        mznVersion = ', '.join(ls[1:])
        return mznVersion
    else:
        return ''


def setup_tuning_folder(args, argGroups):
    # convert all path args to absolute paths
    for argName in ['runDir', 'modelFile', 'evaluationSettingFile', 'targetRunner']:
        setattr(args, argName, os.path.abspath(getattr(args, argName)))    

    # create runDir
    if os.path.isdir(args.runDir):
        print("WARNING: directory " + args.runDir + " already exists")
    else:
        os.mkdir(args.runDir)

    # copy essence model to runDir
    essenceModelFile = args.runDir + '/problem.essence'
    copyfile(args.modelFile, essenceModelFile)

    # run "conjure parameter-generator"
    if args.maxint <= 0:
        print("ERROR: --maxint must be positive")
        sys.exit(1)
    generatorModelFile = args.runDir + '/generator.essence'
    cmd = 'conjure parameter-generator ' + essenceModelFile + ' --MAXINT=' + str(args.maxint) + ' --essence-out ' + generatorModelFile
    run_cmd(cmd)

    # rename irace param file
    move(generatorModelFile + '.irace', args.runDir+'/params.irace')

    # update params.irace and generate params.irace.meta if log-scale is used, as irace doesn't support non-positive parameter lower bounds in that case
    if args.scale=='log':
        iraceParamFile = args.runDir + '/params.irace'
        replace_string(' i ', ' i,log ', iraceParamFile)
        iraceMetaParamFile = iraceParamFile + '.meta'
        scriptDir = get_script_path()
        cmd = 'Rscript ' + scriptDir + '/update-parameter-file.R ' + iraceParamFile + ' ' + scriptDir
        run_cmd(cmd)        

    # generate problem's eprime model
    conjureTempDir = args.runDir + '/conjure-output'
    cmd = 'conjure modelling -ac ' + essenceModelFile + ' -o ' + args.runDir
    run_cmd(cmd)
    move(args.runDir + '/model000001.eprime', args.runDir + '/problem.eprime')

    # generate generator's eprime models
    cmd = 'conjure modelling -ac ' + generatorModelFile + ' -o ' + args.runDir
    run_cmd(cmd)
    move(args.runDir + '/model000001.eprime', args.runDir + '/generator.eprime') 

    # create detailed-output folder and copy all .eprime models file into it
    detailedOutDir = args.runDir + '/detailed-output'
    if os.path.isdir(detailedOutDir) is False:
        os.mkdir(detailedOutDir)
        copy(args.runDir + '/problem.eprime', detailedOutDir)
        copy(args.runDir + '/generator.eprime', detailedOutDir)
    
    # copy other neccessary files
    for fn in ['scenario.txt','instances','run.sh']:
        copy(get_script_path() + '/tuning-files/' + fn, args.runDir)

    # update fields in run.sh
    pbsFile = args.runDir + '/run.sh'
    dictValues = {'seed': args.seed, 'nCores': args.nCores, \
                    'maxExperiments': args.maxExperiments,\
                    'targetRunner': args.targetRunner}
    with open(pbsFile,'rt') as f:
        lsLines = f.readlines()
    for field, value in dictValues.items():
        lsLines = [s.replace('<'+field+'>',str(value)) for s in lsLines]
    with open(pbsFile,'wt') as f:
        f.writelines(lsLines)

    # read evaluation settings
    with open(args.evaluationSettingFile, 'rt') as f:
        evalSettings = json.load(f)

    # write all settings to setting.json
    settingFile = args.runDir + '/setting.json'
    settings = OrderedDict({})
    for group in argGroups.keys():
        settings[group] = OrderedDict()
        for argName in argGroups[group]:
            settings[group][argName] = getattr(args,argName)
    settings['conjure-version'] = get_conjure_version()
    settings['savilerow-version'] = get_SR_version()
    settings['minizinc-version'] = get_minizinc_version()
    settings['evaluationSettings'] = evalSettings
    with open(settingFile,'wt') as f:
        json.dump(settings, f, indent=True)


def main():
    parser = argparse.ArgumentParser(description='Set up a tuning experiment for automated instance generation')    

    # general settings
    parser.add_argument('--runDir',default='./',help='directory where the experiment will be run')
    parser.add_argument('--modelFile',required=True,help='path to a problem specification file in Essence')
    parser.add_argument('--experimentType',required=True,choices=['graded','discriminating'])
    parser.add_argument('--evaluationSettingFile',required=True,help='a JSON file specifying solver settings for the experiment')    
    argGroups = OrderedDict({'generalSettings':['runDir','modelFile','experimentType','evaluationSettingFile']})

    # tuning settings
    parser.add_argument('--maxint',default=100,type=int)
    parser.add_argument('--seed',default=123)
    parser.add_argument('--maxExperiments',default=5000,type=int,help='maximum number of evaluations used by the tuning')
    parser.add_argument('--scale',default='linear',choices=['linear','log'],help='sampling scale for generator parameters')
    parser.add_argument('--nCores',default=1,type=int,help='how many processes running in parallel for the tuning')
    argGroups['tuningSettings'] = ['maxint','seed','maxExperiments','scale','nCores']

    # generator settings
    parser.add_argument('--genSRTimelimit',default=300,help='SR time limit on each generator instance (in seconds)')
    parser.add_argument('--genSRFlags',default='-S0',help='SR extra flags for solving generator instance')
    parser.add_argument('--genSolverTimelimit',default=300,help='time limit for minion to solve a generator instance (in seconds)')
    argGroups['generatorSettings'] = ['genSRTimelimit','genSRFlags','genSolverTimelimit']

    # read from command line args
    args = parser.parse_args()

    # add fixed general settings
    setattr(args, 'targetRunner', get_script_path() + '/tuning-files/target-runner')
    argGroups['generalSettings'].append('targetRunner')
    
    # add fixed generator settings
    setattr(args, 'genSolver','minion')
    setattr(args, 'genSolverFlags', '-varorder domoverwdeg -valorder random -randomiseorder')
    argGroups['generatorSettings'].extend(['genSolver','genSolverFlags'])

    # set up tuning directory
    setup_tuning_folder(args, argGroups)


main()
