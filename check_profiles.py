import json

p = json.load(open('output/profiles/application_people.profile.json'))
print('✅ application_people:')
print(f'  row_count: {p["table_profile"]["row_count_estimate"]}')
print(f'  PK: {p["table_profile"]["pk_candidates"]}')

p2 = json.load(open('output/profiles/Sales_Customers.profile.json'))
print('\n✅ Sales_Customers:')
print(f'  row_count: {p2["table_profile"]["row_count_estimate"]}')
print(f'  PK: {p2["table_profile"]["pk_candidates"]}')
