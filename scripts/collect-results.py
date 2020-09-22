import pandas as pd
import argparse
import subprocess
from shutil import copy
import os
import json


def run_cmd(cmd):
    p = subprocess.run(cmd,shell=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    output = p.stdout.decode('utf-8')
    return output, p.returncode


def main():
    parser = argparse.ArgumentParser(description="collect results after a tuning experiment")    
    parser.add_argument("--runDir", default='./', help='directory where the experiment was run. \nDefault: current folder')
    parser.add_argument("--summaryFile", default='default', help='output of the result collection, saved as a .csv file. Default: <runDir>/summary.csv')
    parser.add_argument("--copyInstancesTo", default=None, help="if set, copy all discriminating instances (instances with baseSolverTime/favouredSolverTime > 1) into a directory. Default: no copy")

    args = parser.parse_args()

    # default summary file
    if args.summaryFile=='default':
        args.summaryFile = args.runDir + '/summary.csv'

    # read instance summary in all out-* files
    resultsDir = args.runDir + '/detailed-output'
    grepCmd = 'grep -h ' + resultsDir + "/out-* -e 'Instance summary: '| cut -d':' -f 2"
    print("Grep instance summary in all out-* files")
    print(grepCmd)
    rs, returnCode = run_cmd(grepCmd)
    if returnCode!=0:
        raise Exception("ERROR: cannot run grep command " + grepCmd)
    
    # convert results into table and write to args.summaryFile as a .csv file
    rsRows = [{item.split('=')[0].strip(): item.split('=')[1].strip() for item in line.split(', ')} for line in rs.split('\n') if line!='']   
    t = pd.DataFrame(rsRows)
    print("Write instance summary to " + args.summaryFile)
    t.to_csv(args.summaryFile, index=False)

    with open(args.runDir + '/setting.json') as f:
        setting = json.load(f)

    # collect results for discriminating instances 
    experimentType = setting['generalSettings']['experimentType']
    if experimentType == 'discriminating':
        # get all instance with ratio>1
        t = t.astype({'ratio':'float'})
        tDis = t[t.ratio>1]
        print("Total number of instances generated: " + str(len(t.instance)))
        print("Total number of discriminating instances (baseSolverTime/favouredSolverTime > 1): " + str(len(tDis.instance)))

        # copy discriminating instances into args.copyInstancesTo
        if args.copyInstancesTo != None:
            # create the folder if needed
            if os.path.isdir(args.copyInstancesTo) is False:
                os.mkdir(args.copyInstancesTo)
            print("Copy discriminating instances into " + args.copyInstancesTo)
            # copy discriminating instances to it
            [copy(resultsDir + '/' + instance + '.param', args.copyInstancesTo) for instance in tDis.instance]        
            # write out summary of those instances 
            tDis.to_csv(args.copyInstancesTo + '/summary.csv', index=False)

    # collect results for graded instances 
    else:
        # get all graded instances
        tGraded = t[t.status=='graded']
        print("Total number of instances generated: " + str(len(t.instance)))
        print("Total number of graded instances: " + str(len(tGraded.instance)))

        # copy discriminating instances into args.copyInstancesTo
        if args.copyInstancesTo != None:
            # create the folder if needed
            if os.path.isdir(args.copyInstancesTo) is False:
                os.mkdir(args.copyInstancesTo)
            print("Copy graded instances into " + args.copyInstancesTo)
            # copy graded instances to it
            [copy(resultsDir + '/' + instance + '.param', args.copyInstancesTo) for instance in tGraded.instance]        
            # write out summary of those instances 
            tGraded.to_csv(args.copyInstancesTo + '/summary.csv', index=False)

main()
