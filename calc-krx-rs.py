#!/usr/bin/env python
import sys
from rs_calculator import run_market_analysis

target_date = sys.argv[1] if len(sys.argv) > 1 else None
run_market_analysis('KRX', target_date=target_date)
