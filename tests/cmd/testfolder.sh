rm -rf foldertest foldertest.INDEX foldertest.CHECKSUM testfolder-stdout testfolder-stdout.CHECKSUM
seamless -cp :testfolder-stdout -cp foldertest \
    'touch test-list.txt | find testfolder -type f -exec md5sum {} \;
    ls
    cp -r testfolder foldertest'
cat testfolder-stdout
cat testfolder-stdout.CHECKSUM
cat foldertest.CHECKSUM
cat foldertest.INDEX
diff -r foldertest testfolder
rm -rf foldertest foldertest.INDEX foldertest.CHECKSUM testfolder-stdout testfolder-stdout.CHECKSUM