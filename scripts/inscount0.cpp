/*
 * Copyright 2002-2020 Intel Corporation.
 * 
 * This software is provided to you as Sample Source Code as defined in the accompanying
 * End User License Agreement for the Intel(R) Software Development Products ("Agreement")
 * section 1.L.
 * 
 * This software and the related documents are provided as is, with no express or implied
 * warranties, other than those that are expressly stated in the License.
 */

#include <iostream>
#include <fstream>
#include <map>
#include <sstream>
#include <set>
#include <string>
#include <stack>
#include "pin.H"

using std::cerr;
using std::ofstream;
using std::ios;
using std::string;
using std::endl;
using std::map;
using std::set;
using std::istringstream;
using std::stack;
using std::pair;

ofstream OutFile;

struct CallStackEntry {
    ADDRINT entryAddr;
    ADDRINT espEntry;
    ADDRINT callSiteAddr;
    int maxDiff;
    string parent;
    string fnName;

    CallStackEntry (ADDRINT entryAddr, ADDRINT espEntry, ADDRINT callSiteAddr) : 
        entryAddr(entryAddr), espEntry(espEntry), callSiteAddr(callSiteAddr) {
            parent = RTN_FindNameByAddress(callSiteAddr);
            fnName = RTN_FindNameByAddress(entryAddr);
            maxDiff = 0;
        }
};

map<ADDRINT, pair<int, string>> maxObservedSize;
map<string, bool> interestingFuncs;

stack<CallStackEntry> callStack;

KNOB<string> KnobOutputFile(KNOB_MODE_WRITEONCE, "pintool",
    "o", "stackSizes.out", "specify output file name");

KNOB<string> KnobInputFile(KNOB_MODE_WRITEONCE, "pintool",
    "i", "addrs.txt", "specify input file name");

BOOL IsIpInteresting(ADDRINT ip) {
    string funcName = RTN_FindNameByAddress(ip);
    auto isInteresting = interestingFuncs.find(funcName);
    if (isInteresting != interestingFuncs.end()) {
        return true;
    } else {
        return false;
    }
}

// This function is called before every instruction is executed
static VOID addStackUpdateEntry(ADDRINT ip, ADDRINT sp) { 
    if (callStack.empty()) {
        return;
    }

    string containingFn = RTN_FindNameByAddress(ip);
    CallStackEntry &topEntry = callStack.top();

    if (topEntry.fnName != containingFn) {
        cerr << "**********************************" << endl;
        cerr << "        Error in execution        " << endl;
        cerr << "Containing Function: " << containingFn << endl;
        cerr << "Current top frame:   " << callStack.top().fnName << endl;
        cerr << "CallStack: " << endl;
        while (!callStack.empty()) {
            cerr << callStack.top().fnName << endl;
            callStack.pop();
        }
        cerr << "**********************************" << endl;
        PIN_ExitApplication(1);
    }

    int currentDiff = topEntry.espEntry - sp;
    topEntry.maxDiff = std::max(topEntry.maxDiff, currentDiff);
    // cerr << std::hex << ip << ":" << std::dec << topEntry.maxDiff << endl;
}

static VOID updateCallStackAtEntry(ADDRINT target, ADDRINT source, ADDRINT sp) {
    string targetFn = RTN_FindNameByAddress(target);
    string sourceFn = RTN_FindNameByAddress(source);

    if (targetFn.find("@plt") != string::npos ||
        !IsIpInteresting(target)) {
        return;
    }

    CallStackEntry entry(target, sp, source);
    callStack.push(entry);
}

static VOID updateCallStackAtExit(ADDRINT target, ADDRINT source, ADDRINT sp) {
    string targetFn = RTN_FindNameByAddress(target);
    string sourceFn = RTN_FindNameByAddress(source);
    // cerr << "Exit from " << sourceFn << " to " << targetFn << endl;
    
    if (callStack.empty()) {
        return;
    }

    ADDRINT entryAddr = callStack.top().entryAddr;
    auto diffSearch = maxObservedSize.find(entryAddr);
    if (diffSearch == maxObservedSize.end()) {
        maxObservedSize[entryAddr] = {0, callStack.top().fnName};
    }

    maxObservedSize[entryAddr].first = std::max(maxObservedSize[entryAddr].first, callStack.top().maxDiff);
    callStack.pop();
}


VOID StackMonitor(INS ins, VOID *v) {
    if (INS_RegWContain(ins, REG_STACK_PTR) ||
        INS_Category(ins) == XED_CATEGORY_CALL ||
        INS_Category(ins) == XED_CATEGORY_PUSH ||
        INS_Category(ins) == XED_CATEGORY_POP ||
        INS_Category(ins) == XED_CATEGORY_RET) {

        if (INS_IsSysenter(ins)) {
            return;
        }

        ADDRINT ip = INS_Address(ins);
        if (!IsIpInteresting(ip)) {
            return;
        }

        IPOINT where = INS_IsValidForIpointAfter(ins) ? IPOINT_AFTER : IPOINT_TAKEN_BRANCH;

        INS_InsertCall(ins, where, 
                (AFUNPTR)addStackUpdateEntry, 
                IARG_REG_VALUE, REG_INST_PTR, 
                IARG_REG_VALUE, REG_STACK_PTR, 
                IARG_END);
    }
}

VOID handleInterFunctionJump(ADDRINT target, ADDRINT source, ADDRINT sp) {
    string targetFn = RTN_FindNameByAddress(target);
    string sourceFn = RTN_FindNameByAddress(source);

    if (callStack.empty()) {
        return;
    }

    callStack.pop();
    if (targetFn.find("@plt") != string::npos ||
        !IsIpInteresting(target)) {
        return;
    }

    CallStackEntry entry(target, sp, source);
    callStack.push(entry);
}

VOID handleIndirectFlow(ADDRINT target, ADDRINT source, ADDRINT sp, BOOL isCall) {
    string targetFn = RTN_FindNameByAddress(target);
    string sourceFn = RTN_FindNameByAddress(source);

    if (!isCall) {
        if (targetFn != sourceFn) {
            callStack.pop();

            if (targetFn.find("@plt") != string::npos ||
                !IsIpInteresting(target)) {
                return;
            }
        
            CallStackEntry entry(target, source, sp);
            callStack.push(entry);
        }
    } else {
        if (targetFn.find("@plt") != string::npos ||
            !IsIpInteresting(target)) {
            return;
        }

        CallStackEntry entry(target, sp, source);
        callStack.push(entry);
    }
}

VOID CallMonitor(INS ins, VOID *v) {
    ADDRINT ip = INS_Address(ins);
    if (!INS_IsControlFlow(ins)) {
        return;
    }

    if (!IsIpInteresting(ip)) {
        return;
    }

    if (INS_IsRet(ins)) {
        INS_InsertCall(ins, IPOINT_TAKEN_BRANCH,
                (AFUNPTR)updateCallStackAtExit,
                IARG_BRANCH_TARGET_ADDR,
                IARG_ADDRINT, ip,
                IARG_REG_VALUE, REG_STACK_PTR,
                IARG_END);
    } else if (INS_IsDirectControlFlow(ins)) {
        ADDRINT target = INS_DirectControlFlowTargetAddress(ins);

        if (INS_IsCall(ins)) {
            INS_InsertCall(ins, IPOINT_TAKEN_BRANCH,
                    (AFUNPTR)updateCallStackAtEntry,
                    IARG_ADDRINT, target,
                    IARG_ADDRINT, ip,
                    IARG_REG_VALUE, REG_STACK_PTR,
                    IARG_END);
        } else {
            if (RTN_FindNameByAddress(target) != RTN_FindNameByAddress(ip)) {
                INS_InsertCall(ins, IPOINT_TAKEN_BRANCH,
                    (AFUNPTR)handleInterFunctionJump,
                    IARG_ADDRINT, target,
                    IARG_ADDRINT, ip,
                    IARG_REG_VALUE, REG_STACK_PTR,
                    IARG_END);
            }
        }
    } else if (INS_IsIndirectControlFlow(ins)) {
        INS_InsertCall(ins, IPOINT_TAKEN_BRANCH,
                (AFUNPTR)handleIndirectFlow,
                IARG_BRANCH_TARGET_ADDR,
                IARG_ADDRINT, ip,
                IARG_REG_VALUE, REG_STACK_PTR,
                IARG_BOOL, INS_IsCall(ins),
                IARG_END);
    }
}

// This function is called when the application exits
VOID Fini(INT32 code, VOID *v)
{
    ofstream result;
    result.open(KnobOutputFile.Value().c_str());
    result << "{";
    for (auto& sizePair : maxObservedSize) {
        result << "\"" << sizePair.second.second << "\":";
        result << sizePair.second.first << ",";
    }
    result.seekp(-1, std::ios_base::end);
    result << "}";
    result.close();

    cerr << "======================" << endl;
    cerr << "Execution done" << endl;
    cerr << "======================" << endl;
}

/* ===================================================================== */
/* Print Help Message                                                    */
/* ===================================================================== */

INT32 Usage()
{
    cerr << "This tool counts max stack runtime stack size per function." << endl;
    cerr << endl << KNOB_BASE::StringKnobSummary() << endl;
    return -1;
}

VOID Image(IMG img, VOID *v) {
    if (IMG_IsMainExecutable(img)) {
        for (SEC sec = IMG_SecHead(img); SEC_Valid(sec); sec = SEC_Next(sec)) {
            if (SEC_Name(sec) != ".text") {
                continue;
            }

            for (RTN rtn = SEC_RtnHead(sec); RTN_Valid(rtn); rtn = RTN_Next(rtn)) {
                interestingFuncs[RTN_Name(rtn)] = true;
            }
        }
    }
}

/* ===================================================================== */
/* Main                                                                  */
/* ===================================================================== */
/*   argc, argv are the entire command line: pin -t <toolname> -- ...    */
/* ===================================================================== */

int main(int argc, char * argv[])
{
    // Initialize pin
    if (PIN_Init(argc, argv)) return Usage();

    PIN_InitSymbols();

    IMG_AddInstrumentFunction(Image, 0);

    // Register StackMonitor to be called when checking stack updates
    INS_AddInstrumentFunction(StackMonitor, 0);

    // Register CallMonitor to be called at function starts and ends
    INS_AddInstrumentFunction(CallMonitor, 0);

    // ParseAddrs();

    // Register Fini to be called when the application exits
    PIN_AddFiniFunction(Fini, 0);
    
    // Start the program, never returns
    PIN_StartProgram();
    
    return 0;
}
