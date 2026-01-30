# API Cost Estimation

This document provides cost estimates for running the full narrative experiment against cloud LLM APIs.

## Source Data Summary

| Metric | Value |
|--------|-------|
| **Total chapters** | 704 (352 original + 352 modified) |
| **Total text** | 17.2 MB (~8.6 MB per variant) |
| **Total words** | ~1.54M (original only) → ~3.08M both variants |
| **Avg words/chapter** | ~4,370 words |

### Books Breakdown

| Book Series | Chapters | Size |
|-------------|----------|------|
| Goosebumps | 68 | 379 KB |
| Harry Potter | 57 | 1.6 MB |
| The Hunger Games | 82 | 1.7 MB |
| The Lord of the Rings | 63 | 2.7 MB |
| Twilight | 82 | 2.3 MB |

## Token Estimation

- **Rule of thumb:** 1 word ≈ 1.3 tokens (English text)
- **Input tokens per chapter:** ~5,680 tokens (text) + ~800 tokens (prompt) ≈ **6,500 tokens**
- **Output tokens per chapter:** ~500-1000 tokens (JSON response) ≈ **750 tokens avg**

### Total Token Usage (Full Experiment)

| Category | Calculation | Total |
|----------|-------------|-------|
| **Input tokens** | 704 chapters × 6,500 | **4.58M tokens** |
| **Output tokens** | 704 chapters × 750 | **528K tokens** |

---

## OpenAI API Pricing

### GPT-5 Series (Latest Flagship - January 2026)
| Model | Input | Output | Total Cost |
|-------|-------|--------|------------|
| **GPT-5.2** | $1.75/1M | $14.00/1M | (4.58M × $1.75) + (0.528M × $14) = **$15.41** |
| **GPT-5 mini** | $0.25/1M | $2.00/1M | (4.58M × $0.25) + (0.528M × $2) = **$2.20** |

### GPT-4.1 Series
| Model | Input | Output | Total Cost |
|-------|-------|--------|------------|
| **GPT-4.1** | $3.00/1M | $12.00/1M | (4.58M × $3.00) + (0.528M × $12) = **$20.08** |
| **GPT-4.1-mini** | $0.80/1M | $3.20/1M | (4.58M × $0.80) + (0.528M × $3.20) = **$5.35** |
| **GPT-4.1-nano** | $0.20/1M | $0.80/1M | (4.58M × $0.20) + (0.528M × $0.80) = **$1.34** |

### GPT-4o Series (Legacy)
| Model | Input | Output | Total Cost |
|-------|-------|--------|------------|
| **GPT-4o** | $2.50/1M | $10.00/1M | (4.58M × $2.50) + (0.528M × $10) = **$16.73** |
| **GPT-4o-mini** | $0.15/1M | $0.60/1M | (4.58M × $0.15) + (0.528M × $0.60) = **$1.00** |

---

## Google Gemini API Pricing

### Gemini 2.x Series
| Model | Input | Output | Total Cost |
|-------|-------|--------|------------|
| **Gemini 2.0 Flash** | $0.10/1M | $0.40/1M | (4.58M × $0.10) + (0.528M × $0.40) = **$0.67** |
| **Gemini 2.0 Flash-Lite** | $0.075/1M | $0.30/1M | (4.58M × $0.075) + (0.528M × $0.30) = **$0.50** |

### Gemini 2.5 Series (Reasoning Models)
| Model | Input | Output | Total Cost |
|-------|-------|--------|------------|
| **Gemini 2.5 Flash-Lite** | $0.10/1M | $0.40/1M | (4.58M × $0.10) + (0.528M × $0.40) = **$0.67** |
| **Gemini 2.5 Flash** | $0.30/1M | $2.50/1M | (4.58M × $0.30) + (0.528M × $2.50) = **$2.69** |
| **Gemini 2.5 Pro** | $1.25/1M | $10.00/1M | (4.58M × $1.25) + (0.528M × $10) = **$11.01** |

### Gemini 3.x Series (Preview)
| Model | Input | Output | Total Cost |
|-------|-------|--------|------------|
| **Gemini 3 Flash Preview** | $0.50/1M | $3.00/1M | (4.58M × $0.50) + (0.528M × $3.00) = **$3.87** |
| **Gemini 3 Pro Preview** | $2.00/1M | $12.00/1M | (4.58M × $2.00) + (0.528M × $12) = **$15.50** |

---

## Cost Summary

| Model | Cost | Speed | Quality |
|-------|------|-------|---------|
| **Gemini 2.0 Flash-Lite** | **$0.50** | Fast | Good |
| **Gemini 2.0 Flash** | **$0.67** | Fast | Better |
| **Gemini 2.5 Flash-Lite** | **$0.67** | Fast | Good+ |
| **GPT-4o-mini** | **$1.00** | Fast | Good |
| **GPT-4.1-nano** | **$1.34** | Fast | Good |
| **GPT-5 mini** | **$2.20** | Fast | Better |
| **Gemini 2.5 Flash** | **$2.69** | Medium | High (reasoning) |
| **GPT-4.1-mini** | **$5.35** | Medium | Better |
| **Gemini 2.5 Pro** | **$11.01** | Medium | High |
| **GPT-5.2** | **$15.41** | Slow | Highest |
| **GPT-4o** | **$16.73** | Slow | High |
| **GPT-4.1** | **$20.08** | Slow | High |

---

## Recommendations

| Budget | Choice | Cost |
|--------|--------|------|
| **Minimal** | Gemini 2.0 Flash-Lite | ~$0.50 |
| **Best value** | Gemini 2.0 Flash | ~$0.67 |
| **Better quality** | GPT-5 mini | ~$2.20 |
| **Quality focus** | Gemini 2.5 Pro or GPT-5.2 | ~$11-15 |

---

## Per-Book Estimates (Harry Potter Only)

For a test run with just Harry Potter (57 chapters × 2 = 114 chapters):

| Model | Cost |
|-------|------|
| Gemini 2.0 Flash-Lite | ~$0.08 |
| Gemini 2.0 Flash | ~$0.11 |
| GPT-4o-mini | ~$0.16 |
| GPT-5 mini | ~$0.36 |
| GPT-5.2 | ~$2.50 |

---

## Local vs Cloud Comparison

### Cost Comparison (Full 704 Chapter Experiment)

| Model | Cost | Infrastructure |
|-------|------|----------------|
| **Qwen 2.5 7B (Local)** | **$0** (electricity only ~$0.50-1) | RTX 3070 Ti 8GB |
| Gemini 2.0 Flash-Lite | $0.50 | Cloud |
| Gemini 2.0 Flash | $0.67 | Cloud |
| Gemini 2.5 Flash-Lite | $0.67 | Cloud |
| GPT-4o-mini | $1.00 | Cloud |
| GPT-4.1-nano | $1.34 | Cloud |
| GPT-5 mini | $2.20 | Cloud |
| Gemini 2.5 Flash | $2.69 | Cloud |
| GPT-4.1-mini | $5.35 | Cloud |
| Gemini 2.5 Pro | $11.01 | Cloud |
| GPT-5.2 | $15.41 | Cloud |
| GPT-4o | $16.73 | Cloud |
| GPT-4.1 | $20.08 | Cloud |

### Quality Comparison

| Model | Parameters | JSON Reliability | Instruction Following | Hallucinations |
|-------|------------|------------------|----------------------|----------------|
| **Qwen 2.5 7B (Local)** | 7B | ⚠️ Medium | ⚠️ Medium | ⚠️ Some loops |
| GPT-4.1-nano | ~8B? | ✅ Good | ✅ Good | ✅ Low |
| GPT-4o-mini | ~8B? | ✅ Good | ✅ Good | ✅ Low |
| Gemini 2.0 Flash | ~? | ✅ Very Good | ✅ Very Good | ✅ Very Low |
| Gemini 2.0 Flash-Lite | ~? | ✅ Good | ✅ Good | ✅ Low |
| GPT-5 mini | ~? | ✅ Very Good | ✅ Very Good | ✅ Very Low |
| Gemini 2.5 Flash | ~? | ✅ Excellent | ✅ Excellent | ✅ Very Low |
| GPT-5.2 | ~? | ✅ Excellent | ✅ Excellent | ✅ Very Low |

### Speed Comparison

| Model | Time per Chapter | Full Experiment (704 ch) |
|-------|-----------------|-------------------------|
| **Qwen 2.5 7B (Local)** | ~60-90s | ~12-18 hours |
| GPT-4o-mini | ~3-5s | ~1 hour |
| GPT-5 mini | ~3-5s | ~1 hour |
| Gemini 2.0 Flash | ~2-4s | ~45 min |
| Gemini 2.0 Flash-Lite | ~2-4s | ~45 min |

### Known Issues with Local Models (Qwen 2.5 7B)

| Issue | Observed | Cloud API Likely |
|-------|----------|------------------|
| Relationship loops (145+) | ✅ Yes | ❌ Unlikely |
| Event loops (96+) | ✅ Yes | ❌ Unlikely |
| Hallucinated deaths | ✅ Yes | ⚠️ Less likely |
| JSON truncation | ✅ Yes | ❌ No (streaming) |
| Slow (4+ min/chapter) | ✅ Sometimes | ❌ No (3-20s) |

### Recommended Strategy

| Goal | Best Choice | Cost |
|------|-------------|------|
| **Free/unlimited testing** | Qwen 2.5 7B (local) | $0 |
| **Cheap + better quality** | Gemini 2.0 Flash | $0.67 |
| **Best value** | GPT-5 mini | $2.20 |
| **Academic paper quality** | GPT-5.2 or Gemini 2.5 Pro | $11-15 |

**Suggested workflow:**
1. Use **Qwen 2.5 7B locally** for prompt/rule iteration (free, unlimited)
2. Run **final experiments on Gemini 2.0 Flash** for paper results (~$0.67)
3. Optional: Run once on **GPT-5.2** for comparison/validation (~$15)

---

## Notes

- Prices as of January 2026
- Actual costs may vary based on:
  - Token counting differences between providers
  - Retry attempts for failed requests
  - Prompt variations
- Consider batch API pricing for additional discounts (OpenAI offers 50% off for batch jobs)

---

*Last updated: 2026-01-30*
