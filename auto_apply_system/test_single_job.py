"""Quick test of single Coinbase job to verify blocker fix."""
import asyncio
import json
import sys
import logging

sys.path.insert(0, '.')

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("test_single")

from applier.greenhouse_applier import GreenhouseApplier

async def test_one():
    with open('greenhouse_matched_jobs.json') as f:
        jobs = json.load(f)['matched_jobs']
    
    job = jobs[2]  # Job #3 with the 'referred' blocker
    logger.info(f"Testing: {job['title']} @ {job['company']}")
    
    applier = GreenhouseApplier()
    try:
        result = await applier.apply(job)
        logger.info(f"Result: {result['status']}")
        if not result['success']:
            logger.info(f"Message: {result['message']}")
        else:
            logger.info("✓ SUCCESS - Application submitted!")
    finally:
        await applier.close()

asyncio.run(test_one())
