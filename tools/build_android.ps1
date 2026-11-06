param([ValidateSet('debug','release','update')][string]$Target = 'debug')
$ErrorActionPreference = 'Stop'
wsl -d TalkApp-Build -u skaven -- bash /mnt/f/Works/Python/talkApp/tools/build_android.sh $Target
if ($LASTEXITCODE -ne 0) { throw "Android build failed (exit $LASTEXITCODE)" }
