echo '# Simple, no conda env, failure'
seamless -c 'cowsay -t "Hello0"'
echo

echo '# Simple, with conda env'
seamless --conda cowsay-environment -c 'cowsay -t "Hello"'
echo

echo '# Multi-step'
seamless --dry --upload --write-job JOB --conda cowsay-environment -c 'cowsay -t "Hello2"'
result=$(seamless-run-transformation JOB/transformation.json.CHECKSUM --delegate --dunder JOB/dunder.json)
echo Result: $result
seamless-download --stdout $result
rm -rf JOB JOB2*
echo

echo '# Multi-step, local execution'
seamless --dry --upload --write-job JOB --conda cowsay-environment -c 'cowsay -t "Hello3"'
result=$(seamless-run-transformation JOB/transformation.json.CHECKSUM --dunder JOB/dunder.json)
echo Result: $result
seamless-download --stdout $result
rm -rf JOB JOB2*
echo

echo '# Multi-step with scratch'
seamless --dry --upload --write-job JOB --conda cowsay-environment -c 'cowsay -t "Hello4"'
result=$(seamless-run-transformation JOB/transformation.json.CHECKSUM --scratch --delegate --dunder JOB/dunder.json)
echo Result: $result
seamless-fingertip --dunder JOB/dunder.json $result
rm -rf JOB JOB2*
echo

echo '# Multi-step with scratch, local execution'
seamless --dry --upload --write-job JOB --conda cowsay-environment -c 'cowsay -t "Hello5"'
result=$(seamless-run-transformation JOB/transformation.json.CHECKSUM --scratch --dunder JOB/dunder.json)
echo Result: $result
seamless-fingertip --dunder JOB/dunder.json $result
rm -rf JOB JOB2*
echo

echo '# Text argument, simple'
echo 'Moo!' > moo.txt
seamless --conda cowsay-environment -c 'moo=$(cat moo.txt); cowsay -t $moo'
rm -f moo.txt moo.txt.CHECKSUM

echo '# Text argument, multi-step, local execution'
echo 'Moo!!' > moo.txt
seamless --dry --write-job JOB --conda cowsay-environment -c 'moo=$(cat moo.txt); cowsay -t $moo'
seamless-upload moo.txt
seamless-upload JOB/transformation.json
seamless-upload JOB/command.txt
seamless-upload JOB/env.json
result=$(seamless-run-transformation JOB/transformation.json.CHECKSUM --dunder JOB/dunder.json)
echo Result: $result
seamless-download --stdout $result
rm -rf moo.txt moo.txt.CHECKSUM JOB

echo '# Composite example'
seamless --dry --upload --write-job JOB --conda cowsay-environment -cp COW.txt -c 'cowsay -t "Hello" > COW.txt; echo OK > OK.txt'
result=$(seamless-run-transformation JOB/transformation.json.CHECKSUM --delegate --dunder JOB/dunder.json)
echo Result: $result
seamless-download -y --directory --output JOB2 $result
cat JOB2/COW.txt
echo
rm -rf JOB JOB2*

echo '# Composite example with scratch'
seamless --dry --upload --write-job JOB --conda cowsay-environment -cp COW.txt -c 'cowsay -t "Hello2" > COW.txt; echo OK > OK.txt'
result=$(seamless-run-transformation JOB/transformation.json.CHECKSUM --delegate --scratch --dunder JOB/dunder.json)
echo Result: $result
seamless-fingertip $result --delegate --dunder JOB/dunder.json --output JOB2.INDEX
seamless-download -y --index JOB2
seamless-fingertip JOB2/COW.txt.CHECKSUM --delegate --dunder JOB/dunder.json --output JOB2/COW.txt
cat JOB2/COW.txt
echo
rm -rf JOB JOB2*

echo '# Composite example, local execution'
seamless --dry --upload --write-job JOB --conda cowsay-environment -cp COW.txt -c 'cowsay -t "Hello3" > COW.txt; echo OK > OK.txt'
result=$(seamless-run-transformation JOB/transformation.json.CHECKSUM --dunder JOB/dunder.json)
echo Result: $result
seamless-download --directory --output JOB2 $result
cat JOB2/COW.txt
echo
rm -rf JOB JOB2*

echo '# Composite example, local execution, with scratch'
seamless --dry --upload --write-job JOB --conda cowsay-environment -cp COW.txt -c 'cowsay -t "Hello4" > COW.txt; echo OK > OK.txt'
result=$(seamless-run-transformation JOB/transformation.json.CHECKSUM --scratch --dunder JOB/dunder.json)
echo Result: $result
seamless-fingertip $result --delegate --dunder JOB/dunder.json --output JOB2.INDEX
seamless-download --index JOB2
seamless-fingertip JOB2/COW.txt.CHECKSUM --dunder JOB/dunder.json --output JOB2/COW.txt
cat JOB2/COW.txt
echo
rm -rf JOB JOB2*