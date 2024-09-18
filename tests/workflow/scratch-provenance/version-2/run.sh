pwd=$(pwd)
seamless-delegate-stop >& /dev/null
rm -rf $pwd/buffers $pwd/database
cp -r $pwd/PRISTINE/buffers $pwd/buffers
cp -r $pwd/PRISTINE/database $pwd/database
export SEAMLESS_HASHSERVER_DIRECTORY=$pwd/buffers
export SEAMLESS_DATABASE_DIRECTORY=$pwd/database
seamless-delegate-stop >& /dev/null
seamless-delegate none >& /dev/null

fing0=2c819b2df5d1bd0b2ff4ed6222ff9539c624bd96119dcd8c4925f07c94f950b7
tf1=0f2af4793506e40080adb7cb77c64747c998056af6f7e048f674a1c99efc4252
fing1=6590a7f7f616a11b7bbf2110c88602362607ec15d02cd7a93d3a4752d20ffc73
tf2=6f6728f9a69768b6ebd3eb021ba05f0f1f4c23fdcf46085f2573b02e9d678905
fing2=fa0e7508a009b78b4737c8a40e9dffbb2db5abec2ce356b734171846f6f9ba7b
tf3=97b90017aed9cad0dbe42154fcbbe08863ef773dca4039bdad40a64232cc3466
fing3=0fa8e64ef53b1cf1b298ee986909c2bbf164e36458663e04b457dd6fad7ae2c4
tf4=396a69adfb1027832cb6ad121fa6de01bb45e71dc61cdd28288fb66cf3a81911

echo Transform 1
seamless-run-transformation $tf1  --fingertip --scratch --verbose --output x
seamless-checksum x
echo $fing0

echo Fingertip 0 
seamless-fingertip $fing0 --verbose --output x
seamless-checksum x
echo $fing0

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