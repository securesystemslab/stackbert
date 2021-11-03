SCRIPT_ROOT=/home/chinmay/Projects/StackBERT
BIN_ROOT=/home/chinmay/SPEC/binaries
ENTRY_EXIT_ROOT=/home/chinmay/Projects/StackBERT/entryExitInfo

function runOne () {
    cd $SCRIPT_ROOT
    local bin=$1
    local optim=$2
    local bits=$3

    python3 stackJsonData.py --file $BIN_ROOT/x$bits/O$optim/$bin --output $ENTRY_EXIT_ROOT/O$optim/$bin.txt
}

function runOneTemp () {
    cd $SCRIPT_ROOT
    local bin=$1
    local optim=$2
    local bits=$3

    if [ ! -f $ENTRY_EXIT_ROOT/O$optim/${bin}_base.binrec-m$bits-O$optim.txt ]; then
        python3 stackJsonData.py --file $BIN_ROOT/x$bits/O$optim/${bin}_base.binrec-m$bits-O$optim --output $ENTRY_EXIT_ROOT/O$optim/${bin}_base.binrec-m$bits-O$optim.txt
    fi
}

# for optim in {0..3}
# do
#     for bin in $(ls ${BIN_ROOT}/x32/O${optim})
#     do
#         runOne $bin $optim 32
#     done
# 
#     for bin in $(ls ${BIN_ROOT}/x64/O${optim})
#     do
#         runOne $bin $optim 64
#     done
# done

# arr=("perlbench_r"  "gcc_r"  "mcf_r" "x264_r" "xz_r" "lbm_r" "imagick_r" "nab_r")
# for optim in {0..3}
# do
#     for bits in 32 64
#     do
#         for bin in $arr
#         do
#             echo "[+] ${bin}_${optim}_${bits}"
#             runOneTemp $bin $optim $bits
#         done
#     done
# done

runOneTemp xz_r 3 32
