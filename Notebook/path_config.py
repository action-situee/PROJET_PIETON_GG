operation_crs = "EPSG:2056"  # Swiss coordinate system
target_crs = "EPSG:4326"  # WGS84 coordinate system


if territoire == 'GG':
    input_file_path = '../../Data/input'
    output_step1_path='../../Data/output/GG/step-1'
    output_step2_path='../../Data/output/GG/step-2'
    output_step3_path='../../Data/output/GG/step-3'

if territoire == 'GE':
    input_file_path = '../../Data/input'
    output_step1_path='../../Data/output/GE/step-1'
    output_step2_path='../../Data/output/GE/step-2'
    output_step3_path='../../Data/output/GE/step-3'