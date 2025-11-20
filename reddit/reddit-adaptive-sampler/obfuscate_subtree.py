#!/usr/bin/env python3
"""
Obfuscate usernames in extracted subtree JSON files.
Works with the current subtree format (author field, replies structure).
"""

import json
import os
import random
from typing import Dict, List, Set
from datetime import datetime


# Default list of common first names
DEFAULT_FIRST_NAMES = [
    "Aaron", "Abigail", "Abram", "Ada", "Addison", "Adelaide", "Adrian", "Adela", "Agnes",
    "Adewale", "Aisha", "Alan", "Albert", "Alexander", "Alexandra", "Alex", "Alexis", "Alice",
    "Allison", "Amanda", "Amara", "Amber", "Amelia", "Amélie", "Amos", "Amy", "Ana", "Ananya",
    "Andrea", "Andre", "Andres", "Andrew", "Andy", "Angel", "Angela", "Anaru", "Annie", "Anthony",
    "Antonio", "April", "Aria", "Arnold", "Arjun", "Arthur", "Ashley", "Audrey", "Austin", "Ava",
    "Ayana", "Barbara", "Barry", "Bao", "Beatrice", "Becky", "Benjamin", "Bernard", "Beth",
    "Bethany", "Betty", "Beverly", "Bill", "Billy", "Blake", "Bob", "Bobby", "Bradley", "Brandon",
    "Brenda", "Brian", "Brittany", "Bruce", "Bryan", "Camila", "Carl", "Carlos", "Camille", "Carol",
    "Carolyn", "Carrie", "Casey", "Catherine", "Cathy", "Charles", "Charlotte", "Chantal", "Chen",
    "Cheryl", "Chidi", "Chris", "Christina", "Christine", "Christopher", "Cindy", "Clarence", "Claude",
    "Clifford", "Clyde", "Cody", "Colin", "Connie", "Corey", "Craig", "Crystal", "Curtis", "Cynthia",
    "Dale", "Dana", "Daniel", "Danielle", "Danny", "Darrell", "David", "Dawn", "Daichi", "Dean",
    "Debbie", "Deborah", "Debra", "Deepa", "Dennis", "Derek", "Diana", "Diane", "Diego", "Donald",
    "Donna", "Doris", "Dorothy", "Douglas", "Drew", "Dylan", "Earl", "Eddie", "Edward", "Edwin",
    "Elaine", "Eleanor", "Elizabeth", "Elena", "Ellen", "Emily", "Emma", "Emery", "Eric", "Erica",
    "Eugene", "Evelyn", "Eva", "Ethan", "Evan", "Faith", "Fatima", "Finley", "Florence", "Frances",
    "Francis", "Frank", "Fred", "Gabriel", "Gabriela", "Gary", "George", "Gerald", "Giulia", "Gloria",
    "Grace", "Gregory", "Hana", "Harold", "Harry", "Haruto", "Hassan", "Hayden", "Heather", "Helen",
    "Henry", "Hina", "Hiroshi", "Howard", "Ian", "Imani", "Isaac", "Isabel", "Ines", "Jack", "Jacob",
    "Jabari", "James", "Jane", "Janet", "Janice", "Jason", "Jean", "Jeffrey", "Jennifer", "Jeremy",
    "Jerry", "Jesse", "Jessica", "Jill", "Jim", "Jimmy", "Jin", "Joan", "Joanne", "Joe", "John",
    "Johnny", "Jonathan", "Jordan", "Jorge", "Jose", "Joseph", "Joshua", "Joyce", "Juan", "Judith",
    "Judy", "Julia", "Julie", "Justin", "Kai", "Karen", "Katarina", "Katherine", "Kathleen", "Kathryn",
    "Kathy", "Keith", "Kelly", "Kenneth", "Kevin", "Keanu", "Kenji", "Khalid", "Kim", "Kimberly",
    "Kiran", "Koa", "Kofi", "Kwame", "Lakshmi", "Lani", "Larry", "Laura", "Lawrence", "Lee", "Leila",
    "Leilani", "Leonard", "Leslie", "Linda", "Lisa", "Li", "Lois", "Louis", "Louise", "Luc", "Luca",
    "Lucian", "Lucia", "Luis", "Lucas", "Lucy", "Lynn", "Madison", "Makoa", "Malik", "Manish", "Marcos",
    "Margaret", "Maria", "Marie", "Marilyn", "Mark", "Marek", "Martha", "Martin", "Mary", "Matthew",
    "Mateo", "Mateusz", "Megan", "Meera", "Melissa", "Michael", "Michelle", "Mika", "Mildred", "Milton",
    "Misty", "Moana", "Monica", "Morgan", "Nancy", "Nadia", "Nabil", "Nathan", "Nicholas", "Nicole",
    "Nikos", "Nia", "Ngozi", "Niko", "Noah", "Noemi", "Noor", "Norma", "Norman", "Olivia", "Oliver",
    "Pamela", "Patricia", "Patrick", "Paul", "Paula", "Parker", "Peggy", "Peter", "Petra", "Philip",
    "Priya", "Rachel", "Ralph", "Randy", "Rangi", "Raymond", "Ravi", "Rebecca", "Reese", "René",
    "Richard", "Riya", "Robert", "Robin", "Roger", "Ronald", "Rosa", "Rose", "Roy", "Ruby", "Russell",
    "Ruth", "Ryan", "Sage", "Salma", "Samantha", "Samuel", "Samir", "Sanjay", "Sandra", "Sara", "Sarah",
    "Scott", "Sean", "Sharon", "Shirley", "Sofia", "Sophia", "Sora", "Stacy", "Stephanie", "Stephen",
    "Steven", "Susan", "Sven", "Sydney", "Tammy", "Tane", "Tariq", "Tatum", "Taylor", "Teresa", "Terry",
    "Theresa", "Thomas", "Timothy", "Tina", "Todd", "Tom", "Tony", "Tomas", "Tui", "Tyler", "Valerie",
    "Valentina", "Victor", "Victoria", "Vikram", "Viktor", "Vincent", "Virginia", "Wanda", "Walter",
    "Wayne", "Wei", "Wendy", "William", "Willie", "Yara", "Yousef", "Yuki", "Yuna", "Zachary", "Zahra",
    "Zoe", "Zuri"
]


def extract_all_usernames(comments: List[Dict]) -> Set[str]:
    """
    Extract all unique usernames from subtree comments.
    
    Args:
        comments: List of comment objects with 'author' field and 'replies'
        
    Returns:
        Set of all unique usernames
    """
    usernames = set()
    
    def traverse(comment_list):
        for comment in comment_list:
            author = comment.get('author', '')
            if author and author != '[deleted]':
                usernames.add(author)
            if 'replies' in comment:
                traverse(comment['replies'])
    
    traverse(comments)
    return usernames


def generate_name_mapping(usernames: Set[str], name_pool: List[str] = None) -> Dict[str, str]:
    """
    Generate mapping from usernames to random first names.
    
    Args:
        usernames: Set of unique usernames
        name_pool: Optional custom list of names
        
    Returns:
        Dictionary mapping original usernames to obfuscated names
    """
    if name_pool is None:
        name_pool = DEFAULT_FIRST_NAMES.copy()
    
    # Shuffle for randomness
    available_names = name_pool.copy()
    random.shuffle(available_names)
    
    if len(usernames) > len(available_names):
        raise ValueError(f"Not enough names. Need {len(usernames)}, have {len(available_names)}")
    
    # Create mapping - all usernames get random names
    username_to_name = {}
    for i, username in enumerate(sorted(usernames)):
        username_to_name[username] = available_names[i]
    
    return username_to_name


def obfuscate_comments(comments: List[Dict], username_mapping: Dict[str, str]) -> List[Dict]:
    """
    Recursively obfuscate usernames in comments.
    
    Args:
        comments: List of comment objects
        username_mapping: Mapping from original to obfuscated usernames
        
    Returns:
        List of comments with obfuscated usernames
    """
    obfuscated = []
    
    for comment in comments:
        obfuscated_comment = comment.copy()
        
        # Obfuscate author
        author = obfuscated_comment.get('author', '')
        if author and author in username_mapping:
            obfuscated_comment['author'] = username_mapping[author]
        # Keep [deleted] as-is
        
        # Recursively obfuscate replies
        if 'replies' in obfuscated_comment:
            obfuscated_comment['replies'] = obfuscate_comments(
                obfuscated_comment['replies'], 
                username_mapping
            )
        
        obfuscated.append(obfuscated_comment)
    
    return obfuscated


def obfuscate_subtree_file(input_file: str, output_file: str = None, 
                          seed: int = None, target_user: str = None) -> Dict:
    """
    Obfuscate usernames in a subtree JSON file.
    
    Args:
        input_file: Path to input subtree JSON file
        output_file: Optional output file path
        seed: Optional random seed for reproducibility
        target_user: Optional target user to map to "TargetUser"
        
    Returns:
        Dictionary with obfuscated data and statistics
    """
    if seed is not None:
        random.seed(seed)
    
    print(f"🔒 Obfuscating usernames in: {input_file}")
    
    # Load data
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Extract usernames from comments
    comments = data.get('comments', [])
    usernames = extract_all_usernames(comments)
    print(f"  📊 Found {len(usernames)} unique usernames")
    
    if not usernames:
        print("  ⚠️  No usernames to obfuscate")
        return data
    
    # Generate mapping (all users get random names, including target_user)
    username_mapping = generate_name_mapping(usernames)
    print(f"  🎭 Generated {len(username_mapping)} name mappings")
    
    # Get target_user from data for display
    target_user = data.get('target_user')
    if target_user and target_user in username_mapping:
        print(f"  👤 Target user ({target_user}) → {username_mapping[target_user]}")
    
    # Create obfuscated data
    obfuscated_data = data.copy()
    obfuscated_data['comments'] = obfuscate_comments(comments, username_mapping)
    
    # Update target_user in metadata
    if target_user and target_user in username_mapping:
        obfuscated_data['target_user'] = username_mapping[target_user]
    
    # Generate output filename
    if output_file is None:
        base_name = os.path.splitext(input_file)[0]
        output_file = f"{base_name}_obfuscated.json"
    
    # Save
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(obfuscated_data, f, indent=2, ensure_ascii=False)
    
    print(f"  ✅ Saved to: {output_file}")
    
    return {
        'input_file': input_file,
        'output_file': output_file,
        'username_mapping': username_mapping,
        'obfuscated_data': obfuscated_data
    }


if __name__ == '__main__':
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python3 obfuscate_subtree.py <subtree_file> [output_file] [seed]")
        sys.exit(1)
    
    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None
    seed = int(sys.argv[3]) if len(sys.argv) > 3 else None
    
    obfuscate_subtree_file(input_file, output_file, seed)

