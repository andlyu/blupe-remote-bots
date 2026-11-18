"""Select the explicitly configured isolated simulation backend."""
import os

if __name__ == '__main__':
    variant = os.environ.get('GEMINI_SIM_VARIANT', 'yam1')
    if variant == 'yam1':
        from yam1_simulation_entry import main
    elif variant == 'reference':
        from reference_simulation_entry import main
    else:
        raise SystemExit('Unknown configured simulation variant')
    main()
