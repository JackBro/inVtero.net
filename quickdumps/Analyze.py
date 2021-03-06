
# MemoryDump is the file we are going to analyze
# Walk detected page tables, logical OS EPROC and more through dynamic language runtime (IronPython)
# Automagically works for XEN, VMWARE, many .DMP versions and RAW!
#
# NO PROFILE CONFIG OR ANYTHING FOR ALL WINDOWS OS!
#
# YOU DO NEED TO HAVE SYMBOLS CONFIGURED.
# IF A GUID IS NOT FOUND, FIND IT MAY BE ON THE SYM CD WHICH IS NOT ON THE SERVER
#
# DLR reflected DIA symbols through physical memory
# make sure to have dia registered do "regsvr32 c:\\windows\system32\msdia120.dll"
# you also want symsrv.dll and dbghelp.dll in the current folder =)
#
#
# Play with the PTType and stuff for nested hypervisors =) (PTTYPE VMCS)
#
#
#MemoryDump = "C:\\Users\\files\\VMs\\Windows Server 2008 x64 Standard\\Windows Server 2008 x64 Standard-ef068a0c.vmem"   
MemoryDump = "C:\\Users\\files\\VMs\\Windows 1511\\Windows.1511.vmem"   
#MemoryDump = "c:\\temp\MC.dmp"
#MemoryDump = "d:\\temp\\2012R2.DMP"
import clr,sys

clr.AddReferenceToFileAndPath("inVtero.net.dll")
clr.AddReferenceToFileAndPath("inVtero.net.ConsoleUtils.dll")

from inVtero.net import *
from inVtero.net.ConsoleUtils import *
from ConsoleUtils import *
from System.IO import Directory, File, FileInfo, Path
from System import Environment, String, Console, ConsoleColor
from System import Text
from System.Diagnostics import Stopwatch

MemoryDumpSize = FileInfo(MemoryDump).Length

# This code fragment can be removed but it's a reminder you need symbols working
sympath = Environment.GetEnvironmentVariable("_NT_SYMBOL_PATH")
if String.IsNullOrWhiteSpace(sympath):
    sympath = "SRV*http://msdl.microsoft.com/download/symbols"

# Basic option handling
# This script can be pretty chatty to stdout 
# 
copts = ConfigOptions()
copts.IgnoreSaveData = False
copts.FileName = MemoryDump
copts.VersionsToEnable = PTType.GENERIC
# To get some additional output 
copts.VerboseOutput = True
copts.VerboseLevel = 1
Vtero.VerboseOutput = True
Vtero.DiagOutput = True

runTime = Stopwatch.StartNew()

# since we are not ignoring SaveData, this just get's our state from
# the underlying protobuf, pretty fast
vtero = Scan.Scanit(copts)

proc_arr = vtero.Processes.ToArray()
low_proc = proc_arr[0]
for proc in proc_arr:
    if proc.CR3Value < low_proc.CR3Value:
        low_proc = proc

proc = low_proc

swModScan = Stopwatch.StartNew()
# if we have save state we can skip this entirely
if vtero.KVS is None or vtero.KVS.Artifacts is None:
    #this thing is pretty expensive right now :(
    #at least it's threaded for you
    vtero.ModuleScan(proc)
    print "Module Scan time: " + swModScan.Elapsed.ToString()

vtero.CheckpointSaveState()

# Symbol scan using GUID & DWORD methods
# If you can't match symbols you can use other API for most goals
for detected in vtero.KVS.Artifacts:
    cv_data = vtero.ExtractCVDebug(proc, detected.Value, detected.Key)
    if cv_data is not None:
        if vtero.TryLoadSymbols(proc, detected.Value, cv_data, detected.Key, sympath):
            vtero.GetKernelDebuggerData(proc, detected.Value, cv_data, sympath)

vtero.CheckpointSaveState()

# Use dynamic typing to walk EPROCES 
logicalList = vtero.WalkProcList(proc)

print "Physical Proc Count: " + proc_arr.Count.ToString()
for pproc in proc_arr:
    print pproc

print "Logical Proc Count: " + logicalList.Count.ToString()

for proc in logicalList:
    # This is due to a structure member name change pre win 8
    if proc.Dictionary.ContainsKey("VadRoot.BalancedRoot.RightChild"):
        proc.VadRoot = proc.Dictionary["VadRoot.BalancedRoot.RightChild"]
    print proc.ImagePath + " : " + proc.Dictionary["Pcb.DirectoryTableBase"].ToString("X") + " : " + proc.VadRoot.ToString("X") +  " : " + proc.UniqueProcessId.ToString("X") 


Console.ForegroundColor = ConsoleColor.Green;
print "Green text is OK++"
print "checking that all logical processes exist in the physical list."
# Miss list mostly bad for yellow printing  
for proc in logicalList:
    found=False
    for hwproc in proc_arr:
        if proc.Dictionary["Pcb.DirectoryTableBase"] == hwproc.CR3Value:
            found=True
    if found == False:
        Console.ForegroundColor = ConsoleColor.Yellow;
        if proc.VadRoot == 0:
            Console.ForegroundColor = ConsoleColor.Green;
        print "Logical miss for " + proc.ImagePath + " : " + proc.Dictionary["Pcb.DirectoryTableBase"].ToString("X") + " : " + proc.VadRoot.ToString("X") +  " : " + proc.UniqueProcessId.ToString("X") 

print "Checking that all physical processes exist in the logical list"
for hwproc in proc_arr:
    Found=False
    for proc in logicalList:
        if proc.Dictionary["Pcb.DirectoryTableBase"] == hwproc.CR3Value:
            found=True
    if found == False:
        Console.ForegroundColor = ConsoleColor.Yellow;
        if proc.VadRoot == 0:
            Console.ForegroundColor = ConsoleColor.Green;
            print "An expected, ",
            print "physical miss for " + proc.ImagePath + " : " + proc.Dictionary["Pcb.DirectoryTableBase"].ToString("X") + " : " + proc.VadRoot.ToString("X") +  " : " + proc.UniqueProcessId.ToString("X") 
 

print "TOTAL RUNTIME: " + runTime.Elapsed.ToString() + " (seconds), INPUT DUMP SIZE: " + MemoryDumpSize.ToString("N") + " bytes."
print "SPEED: " + ((MemoryDumpSize / 1024) / ((runTime.ElapsedMilliseconds / 1000)+1)).ToString("N0") + " KB / second  (all phases aggregate time)"
print "ALL DONE... Please explore!"

# Example of walking process list
def WalkProcListExample():
    #
    #  WALK _EPROCESS LIST
    #
    # Get detected symbol file to use for loaded vtero
    symFile = ""
    for pdb in vtero.KernelProc.PDBFiles:
        if pdb.Contains("ntkrnlmp"):
            symFile = pdb
    # Get a typedef 
    x = vtero.SymForKernel.xStructInfo(symFile,"_EPROCESS")
    ProcListOffsetOf = x.ActiveProcessLinks.Flink.OffsetPos
    ImagePath = ""
    psHead = vtero.GetSymValueLong(vtero.KernelProc,"PsActiveProcessHead")
    _EPROC_ADDR = psHead
    while True:
        memRead = vtero.KernelProc.GetVirtualLong(_EPROC_ADDR - ProcListOffsetOf)
        _EPROC = vtero.SymForKernel.xStructInfo(symFile,"_EPROCESS", memRead)
        # prep and acquire memory for strings
        # TODO: We should scan structures for UNICODE_STRING automatically since extracting them is something * wants
        ImagePtrIndex = _EPROC.SeAuditProcessCreationInfo.ImageFileName.OffsetPos / 8
        ImagePathPtr = memRead[ImagePtrIndex];
        if ImagePathPtr != 0:
            ImagePathArr =  vtero.KernelProc.GetVirtualByte(ImagePathPtr + 0x10); 
            ImagePath = Text.Encoding.Unicode.GetString(ImagePathArr).Split('\x00')[0]
        else:
            ImagePath = ""
        _EPROC_ADDR = memRead[ProcListOffsetOf / 8]
        print "Process ID [" + _EPROC.UniqueProcessId.Value.ToString("X") + "] EXE [" + ImagePath,
        print "] CR3/DTB [" + _EPROC.Pcb.DirectoryTableBase.Value.ToString("X") + "] VADROOT [" + _EPROC.VadRoot.Value.ToString("X") + "]"
        if _EPROC_ADDR == psHead:
            break

