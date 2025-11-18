# sst-containers

The goal is to have workflows to build custom containers that house reproducible experiments here.

A new directory will indicate an experiment, and the scripts to run the experiment will go in there.

There are at least two workflows that I can think of right now:

1. will allow you to specify a branch and commit of SST-core and optionally, SST-elements when dispatching the workflow. The workflow will build and deploy a new container with the tag `(sst-[core,full]-<repo-owner>:<short-sha>`
2. will allow you to specify a base of SST core or full by tag and then add your directory name and then build a new layer from the base sst image and deploy that as `<experiment-name>:latest`



