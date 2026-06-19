Write-Host "====================================================" -ForegroundColor Green
Write-Host " Shatterlands Autopilot Watchdog System Active      " -ForegroundColor Green
Write-Host " Monitoring repository for Jules PR merges...       " -ForegroundColor Green
Write-Host " Interval: Checking every 7 minutes.                " -ForegroundColor Green
Write-Host "====================================================" -ForegroundColor Green

while ($true) {
    # 1. Fetch any open Pull Requests from Jules using the correct field: headRefName
    $openPRs = gh pr list --json headRefName,number,title | ConvertFrom-Json
    
    if ($openPRs) {
        foreach ($pr in $openPRs) {
            # Check if the branch belongs to jules
            if ($pr.headRefName -match "jules") {
                Write-Host "([$(Get-Date -Format 'HH:mm:ss')]) Found active Jules PR: #$($pr.number) - '$($pr.title)'" -ForegroundColor Cyan
                
                # 2. Approve the code changes
                Write-Host "Approving PR #$($pr.number)..." -ForegroundColor Yellow
                gh pr review $($pr.number) --approve
                
                # 3. Merge the PR and delete the temporary cloud branch
                Write-Host "Merging PR #$($pr.number) into main..." -ForegroundColor Yellow
                gh pr merge $($pr.number) --merge --delete-branch
                
                # 4. Sync your local computer immediately!
                Write-Host "Pulling fresh cloud updates down to local repository..." -ForegroundColor Cyan
                git pull origin main --rebase
                
                # 5. Wait for GitHub's database to update, then kick off the next phase
                Write-Host "Waiting 10 seconds for cloud synchronization..." -ForegroundColor Gray
                Start-Sleep -Seconds 10
                
                Write-Host "Triggering next prompt cascade step via workflow_dispatch..." -ForegroundColor Green
                gh workflow run "Shatterlands Zero-Intervention Pipeline"
                
                Write-Host "Handoff complete. Returning to monitoring loop.`n" -ForegroundColor Green
            }
        }
    } else {
        # Prints a timestamped heartbeat so you know it's awake and running
        Write-Host "([$(Get-Date -Format 'HH:mm:ss')]) Repository quiet. Standing by..." -ForegroundColor Gray
    }
    
    # Check your repository every 7 minutes (420 seconds)
    Start-Sleep -Seconds 420
}