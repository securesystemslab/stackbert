PIN=/home/chinmay/Projects/PIN/pin-3.18-98332-gaebd7b1e6-gcc-linux/pin
OBJ_32=/home/chinmay/Projects/PIN/pin-3.18-98332-gaebd7b1e6-gcc-linux/source/tools/ManualExamples/obj-ia32/inscount0.so
OBJ_64=/home/chinmay/Projects/PIN/pin-3.18-98332-gaebd7b1e6-gcc-linux/source/tools/ManualExamples/obj-intel64/inscount0.so
SPEC_ROOT=/home/chinmay/SPEC/binaries/benchspec
ENTRY_EXIT_INFO=/home/chinmay/Projects/StackBERT/entryExitInfo
OUTPUT_ROOT=/home/chinmay/Projects/StackBERT/stackSizeInfo

function runOne () {
    cd $SPEC_ROOT
    local bin=$1
    local optim=$2
    local bits=$3

    cd $bin/O$optim

    if [ $bits -eq 32 ]; then
        value=`cat command-x32`
        $PIN -t $OBJ_32 -o $OUTPUT_ROOT/O$optim/$bin-32.txt -- $value
    fi

    if [ $bits -eq 64 ]; then
        value=`cat command-x64`
        $PIN -t $OBJ_64 -o $OUTPUT_ROOT/O$optim/$bin-64.txt -- $value
    fi
}

# arr=("perlbench_r"  "gcc_r"  "mcf_r" "x264_r" "xz_r" "lbm_r" "imagick_r" "nab_r")
arr=("perlbench_r"  "gcc_r"  "mcf_r" "xz_r" "lbm_r" "nab_r")
for optim in {0..3}
do
    for bits in 32 64
    do
        for bin in ${arr[@]}
        do
            echo "[+] ${bin}_${optim}_${bits}"
            runOne $bin $optim $bits
        done
    done
done
