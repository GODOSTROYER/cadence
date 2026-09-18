$ErrorActionPreference = 'Stop'
$reviewDir = $PSScriptRoot
$identityFields = @('id', 'alias', 'run_id', 'reply_hash', 'rubric_version')
$scoreFields = @('grounded', 'resolves', 'tone', 'safe', 'overall')
$flagFields = @('hallucinated_link_or_policy', 'asks_sensitive_info', 'wrong_issue', 'unsupported_action', 'stale_procedure', 'repeated_known_question', 'wrong_handoff')
$expectedReviewer = 'GPT-6 Astra xhigh independent controls review'
$sha = [System.Security.Cryptography.SHA256]::Create()
function Context-Key($row) {
    return ($row | Select-Object -Property * -ExcludeProperty $identityFields | ConvertTo-Json -Depth 50 -Compress)
}
function Reply-Hash([string]$reply) {
    return ([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($reply)))).Replace('-', '').ToLowerInvariant()
}
function Assert-True($condition, [string]$message) {
    if (-not $condition) { throw $message }
}
$packet = @(Get-Content -LiteralPath (Join-Path $reviewDir 'blind_packet.jsonl') | ForEach-Object { $_ | ConvertFrom-Json -DateKind String })
$unique = @(Get-Content -LiteralPath (Join-Path $reviewDir 'blind_review_unique.jsonl') | ForEach-Object { $_ | ConvertFrom-Json -DateKind String })
Assert-True ($packet.Count -eq 320) 'Expected 320 packet rows.'
Assert-True ($unique.Count -eq 97) 'Expected 97 unique complete contexts.'
$byIndex = @{}
foreach ($part in 1..4) {
    $partPath = Join-Path $reviewDir "blind_ai_ratings_part$part.jsonl"
    $partRatings = @(Get-Content -LiteralPath $partPath | ForEach-Object { $_ | ConvertFrom-Json -DateKind String })
    foreach ($rating in $partRatings) {
        $index = [int]$rating.review_index
        Assert-True (($index -ge 1) -and ($index -le 97)) "Invalid review index $index."
        Assert-True (-not $byIndex.ContainsKey($index)) "Duplicate review index $index."
        $reference = $unique[$index - 1]
        Assert-True ($reference.review_index -eq $index) "Unique packet index mismatch at $index."
        foreach ($field in $identityFields) {
            Assert-True ($rating.$field -ceq $reference.packet.$field) "Identity mismatch at $index / $field."
        }
        Assert-True ($rating.reviewer_type -ceq 'ai') "Invalid reviewer type at $index."
        Assert-True ($rating.reviewer_id -ceq $expectedReviewer) "Invalid reviewer ID at $index."
        Assert-True ($rating.rated_at -match '(Z|[+]00:00)$') "Rating timestamp must explicitly be UTC at $index."
        $timestamp = [DateTimeOffset]::Parse($rating.rated_at)
        Assert-True ($timestamp -le [DateTimeOffset]::UtcNow.AddMinutes(2)) "Future rating timestamp at $index."
        Assert-True (@($rating.scores.PSObject.Properties.Name).Count -eq 5) "Wrong number of score fields at $index."
        foreach ($field in $scoreFields) {
            $value = $rating.scores.$field
            Assert-True (($value -is [int] -or $value -is [long]) -and $value -ge 1 -and $value -le 5) "Invalid score $field at $index."
        }
        Assert-True (@($rating.flags.PSObject.Properties.Name).Count -eq 7) "Wrong number of flags at $index."
        foreach ($field in $flagFields) {
            Assert-True ($rating.flags.$field -is [bool]) "Invalid boolean flag $field at $index."
        }
        Assert-True ($rating.verdict -cin @('ship', 'edit', 'reject')) "Invalid verdict at $index."
        Assert-True ($rating.response_kind -cin @('resolution', 'clarification', 'handoff', 'social', 'other')) "Invalid response kind at $index."
        Assert-True ($rating.severity -cin @('none', 'minor', 'major', 'critical')) "Invalid severity at $index."
        Assert-True (($rating.rationale -is [string]) -and $rating.rationale.Trim().Length -gt 20) "Missing rationale at $index."
        Assert-True ((Reply-Hash $reference.packet.reply_draft) -ceq $rating.reply_hash) "Reply content hash mismatch at $index."
        $byIndex[$index] = $rating
    }
}
Assert-True ($byIndex.Count -eq 97) 'Incomplete unique ratings.'
$byContext = @{}
foreach ($entry in $unique) {
    $context = Context-Key $entry.packet
    Assert-True (-not $byContext.ContainsKey($context)) 'Duplicate allegedly unique context.'
    $byContext[$context] = $byIndex[[int]$entry.review_index]
}
$seen = @{}
$final = @(foreach ($row in $packet) {
    $identityKey = $row.run_id + '|' + $row.id + '|' + $row.alias
    Assert-True (-not $seen.ContainsKey($identityKey)) "Duplicate packet identity $identityKey."
    $seen[$identityKey] = $true
    $context = Context-Key $row
    Assert-True ($byContext.ContainsKey($context)) "No exact context judgment for $identityKey."
    $rating = $byContext[$context]
    Assert-True ((Reply-Hash $row.reply_draft) -ceq $row.reply_hash) "Packet reply hash mismatch for $identityKey."
    $result = [ordered]@{}
    foreach ($field in $identityFields) { $result[$field] = $row.$field }
    foreach ($field in @('reviewer_type', 'reviewer_id', 'rated_at', 'scores', 'flags', 'verdict', 'response_kind', 'severity', 'rationale')) {
        $result[$field] = $rating.$field
    }
    [pscustomobject]$result
})
Assert-True ($final.Count -eq 320) 'Final rating count mismatch.'
$destination = Join-Path $reviewDir 'blind_ai_ratings.jsonl'
$final | ForEach-Object { $_ | ConvertTo-Json -Depth 30 -Compress } | Set-Content -LiteralPath $destination -Encoding utf8
$written = @(Get-Content -LiteralPath $destination | ForEach-Object { $_ | ConvertFrom-Json -DateKind String })
Assert-True ($written.Count -eq $packet.Count) 'Written rating count mismatch.'
for ($i = 0; $i -lt $packet.Count; $i++) {
    foreach ($field in $identityFields) {
        Assert-True ($written[$i].$field -ceq $packet[$i].$field) "Written identity mismatch at row $i / $field."
    }
}
[pscustomobject]@{
    status = 'passed'
    packet_rows = $packet.Count
    unique_contexts = $unique.Count
    completed_ratings = $written.Count
    duplicate_context_rows_reused = $packet.Count - $unique.Count
    reply_hashes_verified = $written.Count
    reviewer_type = 'ai'
    reviewer_id = $expectedReviewer
    checked_at = [DateTime]::UtcNow.ToString('o')
    unblinding_files_read = $false
} | ConvertTo-Json
$sha.Dispose()
