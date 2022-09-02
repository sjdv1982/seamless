# Recipe for a new Seamless project

Seamless is well-suited for remote collaborative projects, where one person is the ***host*** and the others are ***guests***. The host must have Seamless installed, but the guests can be under Windows or any OS, as long as they can install Visual Studio Code.

If you are working solo and don't want remote collaboration, proceed with section B.

## A. Setting up a collaborative project

**Only the host needs to do this. If you are a guest, go to section C.**

1. Install [Visual Studio Code](https://code.visualstudio.com/).

2. Step 3-5 are for hosting on a remote machine (via ssh). If you are hosting from your own local machine, go to step 6. *It is not recommended to host a remote directory that has been mounted locally (sshfs).*

3. In Visual Studio Code, install the Remote Development extension (Ctrl+Shift+X, type "Remote Development").

4. Set up your `~/.ssh/config`.  Below is an example for a machine *gateway* that is accessible directly, and a machine
*workstation* that is only accessible from *gateway*:

```
Host gateway
    HostName 999.999.1.99
    User yourname

Host workstation
    HostName 192.168.1.86
    User yourname
    ProxyCommand ssh -q -W %h:%p gateway
```

To verify that it works, do `ssh workstation` and/or `ssh gateway` from the command line.

5. In Visual Studio Code, connect to the Remote Explorer (icon on the left, or Ctrl-Shift-P => type "Remote Explorer").
Connect to the remote host machine.

6. In Visual Studio Code, type `Ctrl-Shift-(backtick)` to open a new terminal, or use the Terminal menu. Create a new directory PROJDIR, go there. and do `conda activate seamless; seamless-`.

7. In Visual Studio Code, in the File menu, click "Add Folder to Workspace".
After adding the new directory, save the workspace as PROJDIR/PROJNAME, where PROJNAME is the name of the project.

## B. Project initialization

This is for both solo projects and collaborative projects. **For a collaborative project, only the host needs to do this (on the host machine). If you are a guest, go to section C.**

1. On the host machine, install Seamless.

2. Create a new directory PROJDIR. Open a shell in the new directory. Type `seamless-new-project PROJNAME` where `PROJNAME` is the name you choose for your project.

3. If you are an advanced user, now it is the moment to customize version control and set up databases and job handlers. See "Advanced configuration" for more detail.

## C. Project implementation

## Solo projects

1. Open a new terminal and go to PROJDIR. Do `conda activate seamless`.
   The following steps explain how to open your project in Jupyter.
   If you prefer to use IPython instead, go to step 4.

   Type `seamless-jupyter-trusted`. Normally, this will print
   `The Jupyter Notebook is running at: http://localhost:8888/`
   But if port 8888 is already in use, it may be 8889 or a higher number instead.

2. Open the Jupyter window in the browser. A notebook called PROJNAME.ipynb will exist in PROJDIR.

3. Open a second terminal, do `conda activate seamless`, and type `seamless-jupyter-connect` (pressing Tab for completion is recommended).
    This opens a console that connects to the same kernel as the Notebook. From here (or, if you really want, from the Notebook) you can modify `ctx` to implement the topology.

4. Instead of using Jupyter, you can open your project in IPython instead by typing
`seamless-load-project-trusted`.

5. Start the implementation stage. Modify the topology in the console terminal (do `await ctx.translation()` after modification, and type `save()` often!). Mount cells to the file system, and edit them. Monitor error messages in the browser.
You can start visualization in the Jupyter Notebook, then move on to HTML/JS. See [visualization.md TODO LINK]() for more details.

### For collaborative project hosts

**For a collaborative project, only the host needs to do this. If you are a guest, go to the next section**

1. Connect to the host machine. If the project runs on a remote machine, connect to the remote workspace that you set up before, using the Remote Explorer (icon on the left, or Ctrl-Shift-P => type "Remote Explorer") in Visual Studio Code.

2. In Visual Studio Code, install the Live Share extension (Ctrl+Shift+X, type "Live Share").

3. Click on the "Live Share" text at the bottom of the screen and start a Live Share session.

4. At the top of the window, click on "Sign in with  GitHub". This will open a browser window, where you give permission. Follow the instructions.

5. At the bottom, instead of the "Live Share" text, there will now be your GitHub name (it should still be there the next time you start Visual Studio Code).
Click on it, then on "invite others", and paste the link in a message to the guests.

6. Open a new terminal (`Ctrl-Shift-(backtick)` in Visual Studio Code). Do `conda activate seamless`.
   The following steps explain how to open your project in Jupyter.
   If you prefer to use IPython instead, go to step 9.

   Type `seamless-jupyter-trusted`. Normally, this will print
   `The Jupyter Notebook is running at: http://localhost:8888/`
   But if port 8888 is already in use, it may be 8889 or a higher number instead.

   If you are hosting on a remote machine, you must share this port, as well as the Seamless HTTP ports (see step 9).

7. Open the Jupyter window in the browser. A notebook called PROJNAME.ipynb will exist in PROJDIR.

8.  Open a second terminal, do `conda activate seamless`, and type `seamless-jupyter-connect` (pressing Tab for completion is recommended).
    This opens a console that connects to the same kernel as the Notebook. From here (or, if you really want, from the Notebook) you can modify `ctx` to implement the topology.

9. Instead of using Jupyter, you can open your project in IPython instead by typing
`seamless-load-project-trusted`.

10. Now you must decide now much you trust the guests. Note that there is a difference between the *parameters* of the workflow and its *topology*. The *parameters* are the input data and code, whereas the *topology* involves the creation and connection of cells, transformers, cell types, transformer/pin types, and defining mounts and shares. Modification of the topology normally requires re-translation of the workflow (`await ctx.translation`).

    - If you do nothing, guests can only edit files. In the case of file-mounted code cells, this still means arbitrary execution of code.

    - To let them see any web form, you must expose the HTTP ports used by Seamless, which are by default 5138 and 5813 (this is reported in the first Jupyter Notebook output).
    In Visual Studio Code, click again on your name on the bottom and select "Share server" and enter the port number. Once you have shared both ports, you and any guest can see the monitoring at http://localhost:5813/status/status.html

    - To let them help with the topology, you must share the terminal in which the "jupyter console" or "ipython" command is running. Terminals can be shared in the Live Share menu. Note that you can launch arbitrary commands from within a Jupyter console.

    - If you want them to get full Jupyter Notebook access, you must share the Jupyter port (8888). However, Jupyter Notebooks do not really support collaborative editing, so communicate clearly. Note that Jupyter allows you to open new command line terminals in the browser.

11. Start the implementation stage. Modify the topology in the console terminal (do `await ctx.translation()` after modification, and type `save()` often!). Mount cells to the file system, and tell the guests to edit them. Monitor error messages in the browser.
You could start visualization in the Jupyter Notebook, but this will surely give glitches with multiple users. Best to move on early to HTML/JS. See [visualization.md TODO LINK]() for more details.

### For collaborative project guests

1. Install [Visual Studio Code](https://code.visualstudio.com/). This can be the Linux, OSX or Windows version. In theory, you could join from the web version as well, but then you will not be able to see any web forms.

2. In Visual Studio Code, install the Live Share extension (Ctrl+Shift+X, type "Live Share").

3. Click on the "Live Share" text at the bottom of the screen and start a Live Share session.

4. At the top of the window, click on "Sign in with GitHub". This will open a browser window, where you give permission. Follow the instructions.

5. At the bottom, instead of the "Live Share" text, there will now be your GitHub name (it should still be there the next time you start Visual Studio Code).
Click on it, then choose "Join Collaboration Session". Enter the link that the host has provided to you.

6. In the browser, open Jupyter (http://localhost:8888) and the monitoring page (http://localhost:5813/status/status.html). In Jupyter, click on "Running" and then on the notebook.

## D. Advanced configuration

*TODO: expand this section*
(Discuss `/vault` and .gitignore. The vault contains the value for each checksum in
the graph )
TODO in code: save() deletes /vault.
Compare with zips

- Customize load-project. Databases, job handlers.
