import pdb
import os
import pdb
import os
import json

# Path for dataset JSON
JSON_PATH = "dataFiles/dataset.json"
# Path for storing data which can be consumed by fairseq
FAIRSEQROOT = "fairseq"
# Data source directory in fairseq
SRCDIR = "data-src"
# Prefix for directory containing binarized data for finetuning
DIRPREFIX = "finetune-32bitideal-"
# Path where chosen function list is stored
LISTROOT = "funcLists"
# Class buckets for stack sizes
BUCKETS = [8,16,32,64,128,256,512,1024,2048]
# Optimization levels to consider
optimizationLevels = ["O0", "O1", "O2", "O3"]
# Number of max functions to choose per bucket to maintain diversity
PER_SIZE_LIMIT = 2000
# Train-test split ratio
split = 0.8

sizeCounter = {}
allFuncs = {}
selectedFuncs = {}

# Turn on this flag if collecting new data for the same pretrained model
CHOOSE_FROM_PRETRAINED = False
# pretrainFuncs = {}
# if CHOOSE_FROM_PRETRAINED:
#     PRETRAIN_PATH = "/home/chinmay_dd/Projects/varRecovery/scripts/funcLists/pretrain-ideal"
#     with open(os.path.join(PRETRAIN_PATH, "pretrainTrain.txt")) as fp:
#         for func in fp.read().splitlines():
#             pretrainFuncs[func] = "1"

def getDataBytes(byteList):
    return byteList

def getLabel(stackSize):
    return stackSize

def ceilTempLabel(tempLabel):
    for i in BUCKETS:
        if tempLabel <= i:
            return i
    return BUCKETS[-1]

import math
def getUpdatedLabel(value):
    log = math.log(value)
    for i in range(1, 10):
        if log < i:
            break
    return log

if __name__ == "__main__":
    with open(JSON_PATH, "r") as fp:
        allData = json.load(fp)

    if allData is None:
        print("Could not load collected data. Exiting")
        os.exit(1)

    for optimizationLevel in optimizationLevels:
        sizeCounter[optimizationLevel] = {}
        for i in BUCKETS:
            sizeCounter[optimizationLevel][i] = []

    for optimizationLevel in optimizationLevels:
        for func in list(allData.keys())[::-1]:
            if optimizationLevel not in func:
                continue

            tempData = getDataBytes(allData[func]["X"])
            if len(tempData) == 0 and tempData[:1529] not in allFuncs:
                continue

            tempLabel = getLabel(allData[func]["Y"])
            if int(tempLabel) > BUCKETS[-1]:
                continue # Lets not select stacks with > MAX_BUCKET_SIZE bytes

            newLabel = ceilTempLabel(tempLabel)
            if len(sizeCounter[optimizationLevel][newLabel]) > PER_SIZE_LIMIT:
                continue # Already chosen enough from this bucket

            if CHOOSE_FROM_PRETRAINED and func in pretrainFuncs:
                continue

            # Written for regression
            # updatedLabel = getUpdatedLabel(newLabel)

            sizeCounter[optimizationLevel][newLabel].append((tempData, newLabel, func))
            selectedFuncs[func] = 1
            allFuncs[tempData[:1529]] = 1
    
    if not CHOOSE_FROM_PRETRAINED:
        for func in list(allData.keys())[::-1]:
            if func not in selectedFuncs and len(allData[func]["X"]) != 0:
                if allData[func]["X"][:1529] not in allFuncs:
                    pretrainFuncs[func] = allData[func]["X"][:1529]
                    allFuncs[allData[func]["X"][:1529]] = 1

    trainNum = int(len(pretrainFuncs) * 0.8)
    validNum = len(pretrainFuncs) - trainNum
    pretrainTrainFuncs = {}
    pretrainValidFuncs = {}

    counter = 0
    for func in pretrainFuncs:
        if counter < trainNum:
            pretrainTrainFuncs[func] = pretrainFuncs[func]
        else:
            pretrainValidFuncs[func] = pretrainFuncs[func]
        counter += 1

    if not os.path.exists(LISTROOT):
        os.makedirs(LISTROOT)
    
    with open(os.path.join(LISTROOT, "pretrainTrain.txt"), "w") as f:
        for ptFunc in pretrainTrainFuncs:
            f.write(ptFunc)
            f.write("\n")

    with open(os.path.join(LISTROOT, "pretrainValid.txt"), "w") as f:
        for ptFunc in pretrainValidFuncs:
            f.write(ptFunc)
            f.write("\n")
    
    pretrainDir = os.path.join(FAIRSEQROOT, SRCDIR, "pretrain-32bit-ideal")
    if not os.path.exists(pretrainDir):
        os.makedirs(pretrainDir)

    with open(os.path.join(pretrainDir, "train.in"), "w") as f:
        for ptFunc in pretrainTrainFuncs:
            f.write(pretrainTrainFuncs[ptFunc])
            f.write("\n")

    with open(os.path.join(pretrainDir, "valid.in"), "w") as f:
        for ptFunc in pretrainValidFuncs:
            f.write(pretrainValidFuncs[ptFunc])
            f.write("\n")

    for optimizationLevel in optimizationLevels:
        sz = sizeCounter[optimizationLevel]
        trainData  = []
        trainLabel = []
        validData  = []
        validLabel = []
        trainFuncs = []
        validFuncs = []

        for size in sz:
            count = len(sz[size])
            trainLimit = count * split
            counter = 0
            while counter < count:
                if counter < trainLimit:
                    trainData.append(sz[size][counter][0][:1529])
                    trainLabel.append(sz[size][counter][1])
                    trainFuncs.append(sz[size][counter][2])
                else:
                    validData.append(sz[size][counter][0][:1529])
                    validLabel.append(sz[size][counter][1])
                    validFuncs.append(sz[size][counter][2])
                counter += 1

        weights = []
        maxCount = 0
        for size in sorted(sz.keys()):
            maxCount += len(sz[size])

        for size in sorted(sz.keys()):
            weights.append(maxCount/len(sz[size]))

        try:
            os.remove("weights.txt")
        except Exception as e:
            pass

        print("Printing weights if needed for better loss estimation")
        with open("weights.txt", "a+") as fp:
            fp.write(optimizationLevel)
            fp.write("\n")
            fp.write(" ".join([str(x) for x in weights]))
            fp.write("\n")
            print(optimizationLevel)
            print(weights)

        with open(os.path.join(LISTROOT, "train-" + optimizationLevel), "w") as fp:
            fp.write("\n".join(trainFuncs))

        with open(os.path.join(LISTROOT, "valid-" + optimizationLevel), "w") as fp:
            fp.write("\n".join(validFuncs))

        outDir = os.path.join(FAIRSEQROOT, SRCDIR, DIRPREFIX + optimizationLevel)
        if not os.path.exists(outDir):
            os.makedirs(outDir)
        
        with open(os.path.join(outDir, "train.data"), "w") as fp:
            fp.write("\n".join(trainData))

        with open(os.path.join(outDir, "train.label"), "w") as fp:
            for data in trainLabel:
                strData = str(data)
                fp.write(strData)
                fp.write("\n")

        with open(os.path.join(outDir, "valid.data"), "w") as fp:
            fp.write("\n".join(validData))

        with open(os.path.join(outDir, "valid.label"), "w") as fp:
            for data in validLabel:
                strData = str(data)
                fp.write(strData)
                fp.write("\n")
