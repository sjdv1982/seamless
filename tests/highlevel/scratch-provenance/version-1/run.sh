pwd=$(pwd)
seamless-delegate-stop >& /dev/null
rm -rf $pwd/buffers $pwd/database
cp -r $pwd/PRISTINE/buffers $pwd/buffers
cp -r $pwd/PRISTINE/database $pwd/database
export SEAMLESS_HASHSERVER_DIRECTORY=$pwd/buffers
export SEAMLESS_DATABASE_DIRECTORY=$pwd/database
seamless-delegate-stop >& /dev/null
seamless-delegate none >& /dev/null
sleep 2

###fing0=2c819b2df5d1bd0b2ff4ed6222ff9539c624bd96119dcd8c4925f07c94f950b7
tf1=fa275011ce6996dd530180aedab4a583d8eecfdce865534917c1f273ffe7b5a7
fing1=402f64ee85aaaee31551be59230bf641b9e4ccea1453ef37ff19cd48e3f8430f
tf2=b9eb83b3bfdd4eea51aed778fb57a5a669b7369dc0ad3bccddf67ec717a9f20f
fing2=5531b46a7c72c018705a4dfcb66a1c3f9f7ef757d63f4d4545470a1d4b95437d
tf3=f65902dd96dfb7af4c7e517ee4cae038722cb07239ee6d249a2fcd22f6a1606e
fing3=9b6f098a7dbebcf77fdbd8f36e9443feac2db2a36dac363e7b4f1e4f352ce9a8
tf4=396a69adfb1027832cb6ad121fa6de01bb45e71dc61cdd28288fb66cf3a81911

echo Transform 1
seamless-run-transformation $tf1  --fingertip --scratch --verbose --output x
seamless-checksum x
###echo $fing0

###echo Fingertip 0 
###seamless-fingertip $fing0 --verbose --output x
###seamless-checksum x
###echo $fing0

echo Fingertip 1
seamless-fingertip $fing1 --verbose --output x
seamless-checksum x
echo $fing1

echo Transform 2
seamless-run-transformation $tf2  --fingertip --scratch --verbose --output x
seamless-checksum x
echo $fing1

echo Fingertip 2
seamless-fingertip $fing2 --verbose --output x
seamless-checksum x
echo $fing2

echo Transform 3
seamless-run-transformation $tf3  --fingertip --scratch --verbose --output x
seamless-checksum x
echo $fing2

echo Fingertip 3
seamless-fingertip $fing3 --verbose --output x
seamless-checksum x
echo $fing3

echo Transform 4
seamless-run-transformation $tf4  --fingertip --scratch --verbose --output x
seamless-checksum x
echo $fing3

rm -f x
seamless-delegate-stop >& /dev/null
rm -rf $pwd/buffers $pwd/database