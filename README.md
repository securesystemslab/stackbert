Using Transformers to Statically Predict Stack Size Usage of Binary Code
---

This is the repository containing the code for our ACM AISec'21 paper ["StackBERT: Machine Learning Assisted Static Stack Frame Size Recovery on Stripped and Optimized Binaries"](https://dl.acm.org/doi/10.1145/3474369.3486865). Our training sets and pretrained models are hosted on Google Drive.

### Auto-Generating Labels from Open-Source Software
Both LLVM and GCC provide builtin solutions to obtain per-function stack frame sizes during compilation, enabling auto-generation of large amounts of training samples:
```
$ gcc data/input.c -o data/gcc-input -fstack-usage && cat input.su
$ clang data/input.c -o data/gcc-input -fstack-usage && cat input.su
```
This represents the recommended way of obtaining labeled data. However, we also provide tools to obtain ground truth labels from pre-compiled binaries (see stacksyms.py) that we compare against as a baseline. The baseline implementation requires that the binary contains both (i) a symbol table (i.e., a .symtab section), and (ii) call frame information (i.e., an .eh_frames section) as a bare minimum, otherwise function identification and frame calculation will fail. While a debug build is not strictly required, results will usually be better if debug information is present when using the baseline recovery (e.g., because of additional type information).

### Workflow

Experiments can be replicated using the workflow detailed below.

* Run the `mainDriver.py` script to collect stack output for individual binaries. The output of this stage is a folder with an output json for each analyzed binary.
```
{
  "func_name": {
                "inp" : "55 89 ..." <function disassembly>
                "out" : [4,4,4,5...] <stack layout as discerned by stacksyms
               },
   ....
}
```
* Run `dataresolver.py` to collect all data in a single json and remove duplicate functions.
* Run `dataProcessing.py` to binarize data and store it in the form which can be consumed by fairseq. Please edit constants at the top of the code appropriately.
* Create a virtual environment and install pytoch/fairseq. `pip install fairseq` should work just fine.
* Run `fairseq/scripts/pretrain/preprocess.sh` to binarize training data for pretraining task. Please edit paths in the script.
* Run `faiseq/scripts/finetune/preprocess.sh` to binarize training data for finetuning (classification) task. Please edit paths in the scripts.
* Upload generated data in the `data-bin` folder to the `data-bin` folder in the shared drive to use for training.
* Start training using [this Jupyter Notebook](https://github.com/gengrill/stackbert/blob/83e76ddf84171b5f5ab177cda3faa36b30df5d9c/StackSymFinal.ipynb).

### Pretrained Models

Drive Link: https://drive.google.com/drive/folders/1BBduB4-LWLuCJ495m7IOSTgLwMH3EZr3

All models were trained using [this Jupyter Notebook](https://github.com/gengrill/stackbert/blob/83e76ddf84171b5f5ab177cda3faa36b30df5d9c/StackSymFinal.ipynb).

### Dataset

Drive Link: https://drive.google.com/drive/folders/1HUGc2xzKbGUFeCxIB30t_MhrNmbP86d8

Compilers used: GCC 11.1.0 and LLVM 13.0.0. We compile all binaries for both AMD64 and AArch64.

We cannot distribute SPEC 2017 binaries for licensing reasons, but the workflow for building them is exactly the same as for the training set.

### Please cite as follows
```
@inproceedings{aisec2021stackbert,
    author = {Deshpande, Chinmay and Gens, David and Franz, Michael},
    title = {StackBERT: Machine Learning Assisted Static Stack Frame Size Recovery on Stripped and Optimized Binaries},
    year = {2021},
    isbn = {9781450386579},
    publisher = {Association for Computing Machinery},
    address = {New York, NY, USA},
    url = {https://doi.org/10.1145/3474369.3486865},
    doi = {10.1145/3474369.3486865},
    booktitle = {Proceedings of the 14th ACM Workshop on Artificial Intelligence and Security},
    pages = {85–95},
    numpages = {11},
    keywords = {recompilation, machine learning, stack symbolization, binary lifting},
    location = {Virtual Event, Republic of Korea},
    series = {AISec '21}
}
```
