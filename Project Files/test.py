data = [
    {
        'eastings': '123456.456',
        'northings': '789012.012',
        'height': '100.988',
        'Joint Pt ID': '1000-100',
        'Code/-E': 't034',
        'Description': 'ash*'
    }
]

data.append(
    {
        'eastings': '123457.456',
        'northings': '789013.012',
        'height': '101.000',
        'Joint Pt ID': '1000-100',
        'Code/-E': 't035',
        'Description': 'oak*'
})

ktf_data = []

for item in data:
    line = (
        f"{item['eastings']:>12}"
        f"{item['northings']:>12}"
        f"{item['height']:>19}"
        f"{item['Joint Pt ID']:>10}"
        f"{" ":>2}"
        f"{item['Code/-E']:<5}"
        f"{item['Description']}"
    )

    ktf_data.append(line)

#ktf_data = []
#for item in data:
#    ktf_data.append(item['eastings'].rjust(12) + item['northings'].rjust(12) + item['height'].rjust(12) + item['Joint Pt ID'].rjust(13) + item['Code/-E'].rjust(11) + item['Description'].rjust(5))

print("KTF formatted data:")
for line in ktf_data:
    print(line)