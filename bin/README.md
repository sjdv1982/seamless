Client: The machine where /bin/seamless is run with a command string.
Server: The place where the delegation assistant executes the command string.
By default, the *result source* on the server is stdout, and the *result target* is stdout.

The *result source* can only be changed from a .SEAMLESS.yaml / .SEAMLESS.py file.
The *result target* is changed as follows:

The command string is tokenized into bash commands.
Bash command tokens are newline, pipe and ; . Anything between these tokens is a bash command.
Bash redirection tokens are '>', '>>' , '|', '|&', '>&', '2>' and '1>'.

For the last bash command, all redirection tokens are identified.
While the last tokens are '2>' or '1>', they are removed. These become part of the bash code after the added "(...) > RESULT" code.
Then, if the last token is now '>' or '>>', the last command is clipped. Note that the result source remains stdout. In case of '>>', the result target remains stdout.
However, in case of '>', the result target becomes TARGET, which is the file name after '>'. 

Any command ending with "&" is rewritten by seamlessify to: `seamless --detach 'command' &` . The --detach option verifies the result target to have been changed.

Once the result target has been changed: upon launch, /bin/seamless immediately creates a TARGET.JOB file (the file name + .JOB) where the transformation checksum is being written in. It also immediately deletes TARGET, TARGET.CHECKSUM, TARGET.LOG and TARGET.ERROR, if these exist. 
In case of success:
- TARGET.CHECKSUM will contain the result checksum.
- TARGET will contain the result buffer, if it is below --max-download (TODO).
In case of failure:
- TARGET.ERROR will contain the exception. 
In all cases:
- TARGET.LOG will contain the transformation log (if not empty). NOTE: the log will be empty if micro-assistant is being used.

TODO: in a separate thread, touch TARGET.JOB  

TODO: In the command, if a FILE.ext is named where FILE.ext does not exist... 
- ... but FILE.ext.CHECKSUM does, take the checksum. If both exist, verify that the checksum is correct.
- ... but FILE.ext.JOB does, sleep until FILE.ext and/or FILE.ext.CHECKSUM and/or FILE.ext.ERROR exist. Fail whenever FILE.ext.JOB gets stale (not updated for a minute) or deleted.

TODO: support directories

TODO: support name-of-conda-environment. Most assistants should be able to deal with that, if only by preprending "conda activate" (even the micro-assistant could do that).

TODO mid term: for FILE=the first/second argument in the command, read FILE.SEAMLESS.yaml not only for the entire command, but for each tokenized bash command. Unify the results. Unification is trivial in cases of "files", not so easy for "environment". Remember dogma: environments are validations, not recipes! If all Docker image names are the same, no problem, otherwise non-trivial. 

TODO long term: for the non-trivial environments, collate all environments in to a "multi" field, and give it to the assistant to handle. micro-assistant will flat-out refuse.

TODO: long term: for bash/bashdocker transformers that generate more data than fits in memory, adapt the bash/bashdocker transformer executors. What seamless.cmd already does is to set the hash pattern of the output pin to deepfoldercell. To be done: firstly, add a facility to buffer_remote.py to upload a file in chunks to the buffer server, giving back a hash, with low memory consumption. Secondly, add a flag to seamless so that a transformer can tell (forked) seamless that the hash calc has been done already, no need for packing. Thirdly, adapt the executors to do this. This is primarily for running bash under Seamless: A slurm-assistant can do the right thing much easier.