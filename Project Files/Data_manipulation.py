"""
Data_manipulation.py - Data manipulation functions for processing disto and XPAD CSV files.

Reads and processes disto and XPAD CSV files, extracting necessary fields and performing calculations to generate new coordinates. The output is written in KTF format.

Usage from Main.py:
    import Data_manipulation as DM (XX)
    - DM.reduce_disto_output(disto_file, skip_ids=())
    - DM.reduce_xpad_output(xpad_file)
    - DM.calculate_new_coordinates(disto_data, xpad_data)
    - DM.write_to_ktf_format(output_file, new_coordinates)
"""
import csv
import math


def reduce_disto_output(disto_file, skip_ids=()):
    """
    Reduces the disto output to only the necessary fields.
    INPUT:
     - disto_file: The path to the disto output CSV file.
     - skip_ids: Measurement # values to leave out (rows that failed validation).
    OUTPUT:
     - A list of dictionaries containing the reduced data.
     - 'laser_id', 'horizontal_distance', 'azimuth', 'date', 'time', 'tree_code', 'genus', 'tree_radius', 'xpad_id'

    """
    reduced_data = []
    with open(disto_file, newline='') as file:
        reader = csv.DictReader(file)
        for row in reader:
            if row['Measurement #'].strip() in skip_ids:
                continue  # Failed validation - already listed in the validation report
            uncleansed_notes = row['Notes'] 
            
            cleansed_xpad_id, cleansed_tree_code, cleansed_genus = cleanse_notes(uncleansed_notes)
            cleansed_tree_rad = cleanse_tree_dims(cleansed_tree_code)
            reduced_cleansed_row = {
                'laser_id': row['Measurement #'],  # Assuming the first column is Laser ID
                'horizontal_distance': float(row['Horizontal Distance (m)']),
                'vertical_distance': float(row['Vertical Distance (m)']),
                'azimuth': float(row['Azimuth (deg)']),
                'date': row['Date'],
                'time': row['Time'],
                'tree_code': cleansed_tree_code,
                'genus': cleansed_genus + '*', # Add asterisk to genus
                'tree_radius': cleansed_tree_rad, 
                'xpad_id': cleansed_xpad_id
            }
            reduced_data.append(reduced_cleansed_row)
    return reduced_data

def reduce_xpad_output(xpad_file):
    """
    Reduces the XPAD output to only the necessary fields.
    INPUT:
     - xpad_file: The path to the XPAD output CSV file.
    OUTPUT:
     - A list of dictionaries containing the reduced data.
     - 'xpad_id', 'code', 'eastings', 'northings', 'date', 'time'
    """
    reduced_data = []
    with open(xpad_file, newline='') as file:
        reader = csv.DictReader(file)
        for row in reader:
            if row['Code'] != 'LZ':
                continue  # Skip rows that are not laser measurements
            try:
                eastings = float(row['Point East/E'])
                northings = float(row['Point North/N'])
                height = float(row['Point Z/Z'])
            except ValueError:
                continue  # Bad coordinates - already listed in the validation report
            reduced_row = {
                'xpad_id': row['Name'],
                'code': row['Code'],
                'eastings': eastings,
                'northings': northings,
                'height': height,
                'date': row['Date start (local)'],
                'time': row['Time start (local)']
            }
            reduced_data.append(reduced_row)
    return reduced_data

def cleanse_notes(notes):
    """
    Cleanses the notes field to extract XPADID, tree code, and genus.
    Assumes the notes are in the format: "XPADID tree_code genus"
    """
    parts = notes.split()
    if len(parts) < 3:
        return None, None, None  # Not enough information
    xpad_id = parts[0]
    tree_code = parts[1]
    genus = ' '.join(parts[2:])  # In case genus has spaces
    return xpad_id, tree_code, genus

def cleanse_tree_dims(code):
    """
    Takes the code, E.G t034 and returns the tree dimensions, E.G 03 - 0.3 - 0.15m diameter of the tree
    """
    if code.startswith('t'):
        tree_diam = float(code[1:3])/10
        tree_rad = tree_diam/2
        return tree_rad


def calculate_new_coordinates(disto_data, xpad_data):
    """
    Calculates new Eastings, Northings, and Height based on the disto data and xpad data.
    INPUT:
     - disto_data: List of dictionaries containing the reduced disto data.
     - xpad_data: List of dictionaries containing the reduced xpad data.
    OUTPUT:
     - A list of dictionaries containing the new coordinates.
     - 'Description', 'Code/-E', 'Joint Pt ID', 'eastings', 'northings'
    """
    new_ktf_coordinates = []
    for disto_row in disto_data:
        xpad_id = disto_row['xpad_id']
        # Find the corresponding XPAD row
        xpad_row = next((row for row in xpad_data if row['xpad_id'] == xpad_id), None)
        if not xpad_row:
            continue  # No matching XPAD row found

        original_eastings = xpad_row['eastings']
        original_northings = xpad_row['northings']
        original_height = xpad_row['height']

        azimuth_rad = math.radians(disto_row['azimuth'])

        horiz_dist = disto_row['horizontal_distance']
        girth_factor_n = disto_row['tree_radius'] * math.cos(azimuth_rad)
        girth_factor_e = disto_row['tree_radius'] * math.sin(azimuth_rad) 

        new_eastings = original_eastings + girth_factor_e + horiz_dist * math.sin(azimuth_rad)
        new_northings = original_northings + girth_factor_n + horiz_dist * math.cos(azimuth_rad)
        new_height = original_height + disto_row['vertical_distance']

        new_ktf_coordinates.append({
            'Description': disto_row['genus'],
            'Code/-E': disto_row['tree_code'],
            'Joint Pt ID': xpad_id + '-' + disto_row['laser_id'],
            'eastings': f"{new_eastings:.3f}",
            'northings': f"{new_northings:.3f}",
            'height': f"{new_height:.3f}"
        })

    return new_ktf_coordinates

#def write_to_ktf_format(output_file,new_coordinates):
    """
    Converts the new coordinates into KTF 'padded and justified format' and writes to a txt file.
    INPUT:
     - output_file: The path to the output KTF file.
     - new_coordinates: List of dictionaries containing the new coordinates.
    OUTPUT:
        - Writes the new coordinates to the specified output file in KTF format.
    """
    """
    KTF STYLE: 
    Original File name: path
    New E     ,New N     ,ht        , Joint Pt ID , Code/-E  , Description
    12 char JL,12 char JL,12 char JL, 13 char JL  ,10 char JR, 4 char JR
    
    """
    
    
    
    with open(output_file, 'w', newline='') as file:
        writer = csv.writer(file)
        # Write header
        writer.writerow(['Eastings', 'Northings','Joint Pt ID','Code/-E','Description'])
        for new_coord in new_coordinates:
            writer.writerow([
                new_coord['eastings'],
                new_coord['northings'],
                new_coord['Joint Pt ID'],
                new_coord['Code/-E'],
                new_coord['Description']
            ])
